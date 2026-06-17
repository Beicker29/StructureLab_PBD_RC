"""Fiber section model interface."""

from structurelab_pbd_rc.core.exceptions import ModelNotImplementedError


class FiberSection:
    """Future fiber section representation."""

    def build_fibers(self) -> None:
        """Build section fibers.

        TODO: Implement concrete and steel fiber discretization.
        """

        raise ModelNotImplementedError("Fiber section discretization is not implemented yet.")

