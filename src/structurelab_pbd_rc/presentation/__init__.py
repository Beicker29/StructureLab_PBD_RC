"""Presentation adapters that consume structured results without recalculation."""

from structurelab_pbd_rc.presentation.material_characterization import (
    PresentationArtifact,
    build_material_tables,
    render_material_figures,
)
from structurelab_pbd_rc.presentation.section_characterization import (
    SectionPresentationArtifact,
    build_section_tables,
    render_section_figures,
)

__all__ = [
    "PresentationArtifact",
    "SectionPresentationArtifact",
    "build_material_tables",
    "build_section_tables",
    "render_material_figures",
    "render_section_figures",
]
