"""Celery task: parse -> chunk -> embed -> write chunks.

Retries 3x with exponential backoff on transient failures; parse errors
are terminal (retrying won't fix a corrupt file) and mark the file failed
without blocking other files.
"""

import logging
import re
import tempfile
from pathlib import Path

from app.database.db import SessionLocal
from app.database.models import File, FileChunk
from app.integrations import webhooks
from app.parsers.auto_detect import parse_file
from app.parsers.base import ParseError
from app.rag.chunker import chunk_blocks
from app.rag.embedder import embed_texts
from app.security.storage import DecryptionError, read_decrypted
from app.workers.celery_app import celery_app

logger = logging.getLogger("strata.worker")


def _set_status(file_id: int, status: str, error: str | None = None, chunks: int | None = None) -> None:
    with SessionLocal() as db:
        row = db.get(File, file_id)
        if row:
            row.index_status = status
            row.index_error = (error or "")[:2000] or None
            row.is_indexed = status == "ready"
            if chunks is not None:
                row.chunk_count = chunks
            db.commit()


@celery_app.task(
    name="strata.process_file",
    bind=True,
    max_retries=3,
    retry_backoff=True,
    retry_backoff_max=300,
)
def process_file(self, file_id: int) -> str:
    with SessionLocal() as db:
        record = db.get(File, file_id)
        if record is None:
            return "missing"
        if not record.file_path:
            _set_status(file_id, "failed", "stored file path missing")
            return "missing"
        path = Path(record.file_path)
        ext = record.file_type or ""
        doc_name = record.name or path.name

    _set_status(file_id, "processing")
    try:
        # blobs are encrypted at rest; parsers need a plaintext file on disk,
        # so decrypt into a temp file that lives only for the parse
        with tempfile.NamedTemporaryFile(suffix=path.suffix, delete=False) as tmp:
            tmp.write(read_decrypted(path))
            plain = Path(tmp.name)
        try:
            blocks = parse_file(plain, ext)
        finally:
            plain.unlink(missing_ok=True)
    except (ParseError, DecryptionError, OSError) as exc:
        logger.error("parse failed for file %s: %s", file_id, exc)
        _set_status(file_id, "failed", str(exc))
        webhooks.notify("file.failed", {"file_id": file_id, "name": doc_name, "error": str(exc)})
        return "parse_error"

    chunks = chunk_blocks(blocks)
    if not chunks:
        _set_status(file_id, "failed", "no extractable text")
        return "empty"

    # contextual chunk header: file name woven into the indexed text, so both
    # the tsvector (via the DB trigger) and the embedding carry it
    doc_tag = re.sub(r"[-_]+", " ", Path(doc_name).stem).strip()
    for c in chunks:
        c.text = f"[Document: {doc_tag}]\n{c.text}"

    try:
        vectors = embed_texts([c.text for c in chunks])
    except Exception as exc:
        # transient (model load, redis, OOM), retry with backoff, then fail
        if self.request.retries >= self.max_retries:
            _set_status(file_id, "failed", f"embedding failed: {exc}")
            return "embed_error"
        raise self.retry(exc=exc)

    with SessionLocal() as db:
        # idempotent on retry: replace any chunks from a previous attempt
        db.query(FileChunk).filter(FileChunk.file_id == file_id).delete()
        db.add_all(
            FileChunk(
                file_id=file_id,
                chunk_text=c.text,
                embedding=v,
                page_number=c.page,
                section_title=c.section,
                chunk_index=c.index,
                metadata_=c.metadata or None,
            )
            for c, v in zip(chunks, vectors)
        )
        db.commit()

    _set_status(file_id, "ready", chunks=len(chunks))
    logger.info("indexed file %s: %d chunks", file_id, len(chunks))
    return "ready"
