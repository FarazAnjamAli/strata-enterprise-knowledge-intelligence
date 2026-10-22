"""XLSX and CSV parsing. Each sheet becomes blocks of pipe-delimited rows
with the header repeated, so table structure survives chunking."""

from pathlib import Path

import pandas as pd

from app.parsers.base import ParsedBlock, ParseError

ROWS_PER_BLOCK = 40  # keeps blocks well under chunk size


def _frame_blocks(df: pd.DataFrame, section: str) -> list[ParsedBlock]:
    if df.empty:
        return []
    df = df.fillna("")
    header = " | ".join(str(c) for c in df.columns)
    blocks = []
    for start in range(0, len(df), ROWS_PER_BLOCK):
        part = df.iloc[start : start + ROWS_PER_BLOCK]
        rows = "\n".join(" | ".join(str(v) for v in row) for row in part.itertuples(index=False))
        blocks.append(
            ParsedBlock(
                text=f"{header}\n{rows}",
                section=section,
                metadata={"rows": f"{start + 1}-{start + len(part)}"},
            )
        )
    return blocks


def parse_xlsx(path: Path) -> list[ParsedBlock]:
    try:
        sheets = pd.read_excel(path, sheet_name=None)
    except Exception as exc:
        raise ParseError(f"XLSX parse failed: {exc}") from exc
    blocks = []
    for name, df in sheets.items():
        blocks.extend(_frame_blocks(df, section=f"sheet: {name}"))
    return blocks


def parse_csv(path: Path) -> list[ParsedBlock]:
    try:
        with path.open("rb") as f:
            bom = f.read(2)
        # same BOM sniff as text._read, upload validation accepts UTF-16
        encoding = "utf-16" if bom in (b"\xff\xfe", b"\xfe\xff") else "utf-8"
        df = pd.read_csv(path, on_bad_lines="skip", encoding=encoding)
    except Exception as exc:
        raise ParseError(f"CSV parse failed: {exc}") from exc
    return _frame_blocks(df, section="csv")
