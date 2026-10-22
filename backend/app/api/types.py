"""Shared request types."""

import re
from typing import Annotated

from pydantic import AfterValidator, StringConstraints

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _email(v: str) -> str:
    # deliberately permissive: on-prem directories use .local / .lan / .corp
    # domains that strict validators reject as "special-use"
    v = v.strip().lower()
    if not _EMAIL.match(v):
        raise ValueError("enter a valid email address")
    return v


Email = Annotated[str, StringConstraints(max_length=255), AfterValidator(_email)]
