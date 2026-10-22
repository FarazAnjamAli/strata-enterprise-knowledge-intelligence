"""Video files: metadata-only indexing (no transcription in MVP).

One block carrying the filename and basic facts, so the file is findable
by name/keyword search; the answer's source chip is the play/download link.
"""

from pathlib import Path

from app.parsers.base import ParsedBlock


def parse(path: Path) -> list[ParsedBlock]:
    # the worker prepends the real document name to every chunk, so the
    # block only needs the facts the path can vouch for
    size_mb = path.stat().st_size / (1024 * 1024)
    return [
        ParsedBlock(
            text=(
                f"Video file. Format: {path.suffix.lstrip('.').upper()}, {size_mb:.1f} MB.\n"
                "Content is not transcribed; open the source file to watch it."
            ),
            metadata={"video": True},
        )
    ]
