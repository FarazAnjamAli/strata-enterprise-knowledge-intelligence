"""Parser interface. Each parser turns a file into ParsedBlocks that keep
enough provenance (page, section) for citations."""

from dataclasses import dataclass, field


@dataclass
class ParsedBlock:
    text: str
    page: int | None = None
    section: str | None = None
    metadata: dict = field(default_factory=dict)


class ParseError(Exception):
    pass


# extension -> parse function; populated by auto_detect at import time
Parser = "callable[[Path], list[ParsedBlock]]"
