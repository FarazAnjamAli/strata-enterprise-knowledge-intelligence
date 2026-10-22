"""Extension -> parser routing plus magic-byte validation.

Magic checks are hand-rolled (no libmagic dependency): binary formats have
reliable signatures; text formats are validated by decodability instead.
"""

from pathlib import Path

from app.parsers import docx as docx_parser
from app.parsers import image as image_parser
from app.parsers import pdf as pdf_parser
from app.parsers import tabular, text
from app.parsers import video as video_parser
from app.parsers.base import ParsedBlock, ParseError

PARSERS = {
    "pdf": pdf_parser.parse,
    "docx": docx_parser.parse,
    "xlsx": tabular.parse_xlsx,
    "csv": tabular.parse_csv,
    "txt": text.parse_txt,
    "md": text.parse_md,
    "json": text.parse_json,
    "xml": text.parse_xml,
    "png": image_parser.parse,
    "jpg": image_parser.parse,
    "jpeg": image_parser.parse,
    "mp4": video_parser.parse,
    "mov": video_parser.parse,
    "avi": video_parser.parse,
    "mkv": video_parser.parse,
}

_MAGIC = {
    "pdf": [b"%PDF"],
    "docx": [b"PK\x03\x04"],  # OOXML zip container
    "xlsx": [b"PK\x03\x04"],
    "png": [b"\x89PNG"],
    "jpg": [b"\xff\xd8\xff"],
    "jpeg": [b"\xff\xd8\xff"],
}

_TEXT_EXTENSIONS = {"csv", "txt", "md", "json", "xml"}


def validate_magic_bytes(head: bytes, ext: str) -> bool:
    """head = first bytes of the file (>= 8). True if content matches ext."""
    ext = ext.lower()
    if ext in ("mp4", "mov"):
        return head[4:8] == b"ftyp"  # ISO base media: size(4) + 'ftyp'
    if ext == "avi":
        return head.startswith(b"RIFF") and head[8:12] == b"AVI "
    if ext == "mkv":
        return head.startswith(b"\x1a\x45\xdf\xa3")  # EBML
    if ext in _MAGIC:
        return any(head.startswith(sig) for sig in _MAGIC[ext])
    if ext in _TEXT_EXTENSIONS:
        # UTF-16 (Windows Notepad default "Unicode") legitimately contains
        # null bytes, accept it by its BOM.
        if head.startswith((b"\xff\xfe", b"\xfe\xff")):
            return True
        # A UTF-8 decode check false-negatives when the sample cuts a
        # multibyte char; absence of null bytes is the robust signal.
        return b"\x00" not in head
    return False


def parse_file(path: Path, ext: str) -> list[ParsedBlock]:
    parser = PARSERS.get(ext.lower())
    if parser is None:
        raise ParseError(f"no parser for extension: {ext}")
    return parser(path)
