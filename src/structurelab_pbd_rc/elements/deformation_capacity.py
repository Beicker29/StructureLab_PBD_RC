"""Element deformation capacity interface."""

from structurelab_pbd_rc.core.exceptions import ModelNotImplementedError


def calculate_deformation_capacity(*args, **kwargs):
    """Calculate deformation capacity.

    TODO: Implement for columns, beams and plastic hinge regions.
    """

    raise ModelNotImplementedError("Deformation capacity is not implemented yet.")

