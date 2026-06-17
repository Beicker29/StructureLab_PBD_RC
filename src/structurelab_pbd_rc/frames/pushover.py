"""Pushover analysis interface."""

from structurelab_pbd_rc.core.exceptions import ModelNotImplementedError


def run_pushover_analysis(*args, **kwargs):
    """Run pushover analysis.

    TODO: Implement static nonlinear analysis workflow after element models exist.
    """

    raise ModelNotImplementedError("Pushover analysis is not implemented yet.")

