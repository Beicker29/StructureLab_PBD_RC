"""Column element interface."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Column:
    """Future reinforced concrete column model."""

    name: str

