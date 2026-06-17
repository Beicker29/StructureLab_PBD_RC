"""Frame geometry interfaces."""

from dataclasses import dataclass


@dataclass(frozen=True)
class FrameGeometry:
    """Future planar frame geometry container."""

    name: str

