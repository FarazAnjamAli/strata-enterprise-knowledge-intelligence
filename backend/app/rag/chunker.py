"""Boundary-aware chunking.

Token counts are approximated as words / 0.75 (≈1.33 tokens per word),
which keeps chunks safely under the 512-token spec limit without pulling
in a tokenizer dependency.
"""

from dataclasses import dataclass, field

from app.parsers.base import ParsedBlock

MAX_TOKENS = 512
OVERLAP_TOKENS = 50
_WORDS_PER_TOKEN = 0.75
MAX_WORDS = int(MAX_TOKENS * _WORDS_PER_TOKEN)  # 384
OVERLAP_WORDS = int(OVERLAP_TOKENS * _WORDS_PER_TOKEN)  # 37


@dataclass
class Chunk:
    text: str
    index: int
    page: int | None = None
    section: str | None = None
    metadata: dict = field(default_factory=dict)


def _split_long(words: list[str]) -> list[list[str]]:
    """Split an over-long word list into overlapping windows."""
    parts = []
    step = MAX_WORDS - OVERLAP_WORDS
    for start in range(0, len(words), step):
        part = words[start : start + MAX_WORDS]
        parts.append(part)
        if start + MAX_WORDS >= len(words):
            break
    return parts


def chunk_blocks(blocks: list[ParsedBlock]) -> list[Chunk]:
    """Pack paragraphs into chunks up to MAX_WORDS, never merging across
    pages/sections/tables (those boundaries carry citation meaning)."""
    chunks: list[Chunk] = []

    for block in blocks:
        paragraphs = [p.strip() for p in block.text.split("\n\n") if p.strip()]
        buf: list[str] = []
        buf_words = 0

        def flush(block: ParsedBlock = block) -> None:
            nonlocal buf, buf_words
            if buf:
                chunks.append(
                    Chunk(
                        text="\n\n".join(buf),
                        index=len(chunks),
                        page=block.page,
                        section=block.section,
                        metadata=block.metadata,
                    )
                )
                buf, buf_words = [], 0

        for para in paragraphs:
            words = para.split()
            if len(words) > MAX_WORDS:
                flush()
                for part in _split_long(words):
                    chunks.append(
                        Chunk(
                            text=" ".join(part),
                            index=len(chunks),
                            page=block.page,
                            section=block.section,
                            metadata=block.metadata,
                        )
                    )
                continue
            if buf_words + len(words) > MAX_WORDS:
                flush()
            buf.append(para)
            buf_words += len(words)
        flush()

    return chunks
