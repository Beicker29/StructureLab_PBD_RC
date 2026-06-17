"""Frame loading interfaces."""

from dataclasses import dataclass


@dataclass(frozen=True)
class LoadCase:
    """Named load case placeholder."""

    name: str

