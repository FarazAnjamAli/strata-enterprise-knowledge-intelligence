from pathlib import Path

import pdfplumber

from app.parsers.base import ParsedBlock, ParseError


def _clean(cell) -> str:
    return "" if cell is None else " ".join(str(cell).split()).strip()


def _table_to_text(table: list[list]) -> str:
    """Render a table so cell-to-header relationships survive.

    A flat 'a | b | c' dump lets the LLM mis-pair values (e.g. read a RACI
    matrix code as someone's job title). Instead, when the first row looks
    like a header, every data row becomes explicit 'Header: value' pairs so
    'Name: Ameen Ahsan, Designation: CEO' can never be misread.
    """
    rows = [[_clean(c) for c in row] for row in table if row]
    rows = [r for r in rows if any(r)]  # drop fully-empty rows
    if not rows:
        return ""

    header = rows[0]
    header_is_labels = sum(1 for h in header if h) >= max(2, len(header) - 1) and all(
        len(h) <= 40 for h in header
    )

    # single-column or headerless: keep a simple readable list
    if len(header) < 2 or not header_is_labels:
        return "\n".join(" | ".join(c for c in r if c) for r in rows if any(r))

    out: list[str] = []
    for r in rows[1:]:
        pairs = [f"{header[i]}: {r[i]}" for i in range(min(len(header), len(r))) if header[i] and r[i]]
        if pairs:
            out.append("; ".join(pairs))
    # nothing but the header row -> fall back to the header itself
    return "\n".join(out) if out else " | ".join(h for h in header if h)


def parse(path: Path) -> list[ParsedBlock]:
    blocks: list[ParsedBlock] = []
    try:
        with pdfplumber.open(path) as pdf:
            for page_no, page in enumerate(pdf.pages, start=1):
                text = page.extract_text() or ""
                if text.strip():
                    blocks.append(ParsedBlock(text=text, page=page_no))
                for t_idx, table in enumerate(page.extract_tables()):
                    rendered = _table_to_text(table) if table else ""
                    if rendered.strip():
                        blocks.append(
                            ParsedBlock(
                                text=f"[Table]\n{rendered}",
                                page=page_no,
                                section=f"table {t_idx + 1}",
                                metadata={"table": t_idx + 1},
                            )
                        )
    except Exception as exc:
        raise ParseError(f"PDF parse failed: {exc}") from exc
    return blocks
