"""Axial-moment interaction diagram interface."""

from structurelab_pbd_rc.core.exceptions import ModelNotImplementedError


def build_interaction_diagram(*args, **kwargs):
    """Build a section interaction diagram.

    TODO: Implement axial load and curvature sweep.
    """

    raise ModelNotImplementedError("Interaction diagram generation is not implemented yet.")

