"""Financial data masking, applied to any text leaving the trust boundary
(Tier 3 Ollama prompts today, Tier 4 external APIs in Phase 4).

Two classes of pattern:
 1. Currency-tagged amounts anywhere ($1,234.56 / PKR 50,000 / Rs. 2.5M)
 2. Bare numbers adjacent to a financial keyword (salary, revenue, ...)
 3. Long digit runs (8+) that look like account numbers
"""

import re

from app.config import get_settings

MASK = "[MASKED]"

_CURRENCY = r"(?:\$|€|£|₨|PKR|Rs\.?|USD|EUR|GBP|AED|SAR)"
_NUMBER = r"\d[\d,]*(?:\.\d+)?\s*(?:k|K|m|M|bn|B|million|billion|thousand|lakh|crore)?"

_CURRENCY_AMOUNT = re.compile(rf"{_CURRENCY}\s*{_NUMBER}", re.IGNORECASE)
_ACCOUNT_NUMBER = re.compile(r"\b\d[\d\- ]{10,}\d\b|\b\d{8,}\b")


def _keyword_pattern(keywords: list[str]) -> re.Pattern:
    kw = "|".join(re.escape(k) for k in keywords)
    # "salary: 250,000" / "the revenue was 1.2M", number within a few words
    return re.compile(
        rf"\b(?P<kw>{kw})(?P<mid>s?\w*(?:\s+\S+){{0,4}}?[\s:=-]+){_CURRENCY}?\s*(?P<num>{_NUMBER})",
        re.IGNORECASE,
    )


def mask_financial_data(text: str) -> str:
    settings = get_settings()
    if not settings.enable_financial_masking:
        return text

    text = _CURRENCY_AMOUNT.sub(MASK, text)
    pattern = _keyword_pattern(settings.masking_keywords)
    text = pattern.sub(lambda m: f"{m.group('kw')}{m.group('mid')}{MASK}", text)
    text = _ACCOUNT_NUMBER.sub(MASK, text)
    return text
