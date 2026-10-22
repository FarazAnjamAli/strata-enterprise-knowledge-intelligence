"""Query sanitation before anything reaches a prompt or tsquery."""

import re

from app.config import get_settings

MAX_QUERY_CHARS = 2000

# Common prompt-injection framings; neutralized rather than rejected so
# legitimate questions containing these words still get answered.
_INJECTION = re.compile(
    r"(ignore (all )?(previous|above|prior) (instructions|prompts?)"
    r"|disregard (the )?(system|previous) (prompt|instructions)"
    r"|you are now\b"
    r"|act as (an? )?(different|new) (ai|assistant|system)"
    r"|reveal (your )?(system )?prompt)",
    re.IGNORECASE,
)


def sanitize_query(query: str) -> str:
    query = query.replace("\x00", " ").strip()
    query = query[:MAX_QUERY_CHARS]
    if get_settings().enable_prompt_injection_protection:
        query = _INJECTION.sub("[removed]", query)
    return query
