from pathlib import Path

import pytesseract
from PIL import Image

from app.config import get_settings
from app.parsers.base import ParsedBlock, ParseError


def parse(path: Path) -> list[ParsedBlock]:
    settings = get_settings()
    if not settings.enable_ocr:
        return []
    try:
        with Image.open(path) as img:
            text = pytesseract.image_to_string(img, lang=settings.ocr_language)
    except Exception as exc:
        raise ParseError(f"OCR failed: {exc}") from exc
    text = text.strip()
    return [ParsedBlock(text=text, metadata={"ocr": True})] if text else []
