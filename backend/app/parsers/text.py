"""Plain text, markdown, JSON and XML parsing (stdlib only)."""

import json
from pathlib import Path
from xml.etree.ElementTree import ParseError as XMLParseError

import defusedxml.ElementTree as ET

from app.parsers.base import ParsedBlock, ParseError


def _read(path: Path) -> str:
    try:
        raw = path.read_bytes()
    except Exception as exc:
        raise ParseError(f"text read failed: {exc}") from exc
    # BOM-sniff: Windows Notepad saves "Unicode" as UTF-16 with a BOM
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16", errors="replace")
    return raw.decode("utf-8-sig", errors="replace")


def parse_txt(path: Path) -> list[ParsedBlock]:
    text = _read(path)
    return [ParsedBlock(text=text)] if text.strip() else []


def parse_md(path: Path) -> list[ParsedBlock]:
    """Split on headings so section titles survive as citation context."""
    blocks: list[ParsedBlock] = []
    section = None
    buf: list[str] = []

    def flush():
        text = "\n".join(buf).strip()
        if text:
            blocks.append(ParsedBlock(text=text, section=section))
        buf.clear()

    for line in _read(path).splitlines():
        if line.lstrip().startswith("#"):
            flush()
            section = line.lstrip("# ").strip()
        else:
            buf.append(line)
    flush()
    return blocks


def _flatten(obj, prefix="") -> list[str]:
    lines = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            lines.extend(_flatten(v, f"{prefix}{k}."))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            lines.extend(_flatten(v, f"{prefix}{i}."))
    else:
        lines.append(f"{prefix.rstrip('.')}: {obj}")
    return lines


def parse_json(path: Path) -> list[ParsedBlock]:
    try:
        data = json.loads(_read(path))
    except json.JSONDecodeError as exc:
        raise ParseError(f"JSON parse failed: {exc}") from exc
    return [ParsedBlock(text="\n".join(_flatten(data)))]


def parse_xml(path: Path) -> list[ParsedBlock]:
    try:
        root = ET.fromstring(_read(path))
    except (XMLParseError, ValueError) as exc:
        raise ParseError(f"XML parse failed: {exc}") from exc
    lines = []
    for el in root.iter():
        text = (el.text or "").strip()
        if text:
            lines.append(f"{el.tag}: {text}")
    return [ParsedBlock(text="\n".join(lines))] if lines else []
