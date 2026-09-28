"""V2 workflow stage boundaries implemented to date."""

from structurelab_pbd_rc.workflow.stages.project_objectives import (
    MODULE_ID as PROJECT_OBJECTIVES_MODULE_ID,
    STAGE_NUMBER as PROJECT_OBJECTIVES_STAGE_NUMBER,
    evaluate_project_objectives,
)
from structurelab_pbd_rc.workflow.stages.site_hazard import (
    MODULE_ID as SITE_HAZARD_MODULE_ID,
    STAGE_NUMBER as SITE_HAZARD_STAGE_NUMBER,
    execute_site_hazard,
)
from structurelab_pbd_rc.workflow.stages.material_characterization import (
    MODULE_ID as MATERIAL_CHARACTERIZATION_MODULE_ID,
    STAGE_NUMBER as MATERIAL_CHARACTERIZATION_STAGE_NUMBER,
    execute_material_characterization,
)
from structurelab_pbd_rc.workflow.stages.section_component_characterization import (
    MODULE_ID as SECTION_COMPONENT_CHARACTERIZATION_MODULE_ID,
    STAGE_NUMBER as SECTION_COMPONENT_CHARACTERIZATION_STAGE_NUMBER,
    execute_section_component_characterization,
)

__all__ = [
    "MATERIAL_CHARACTERIZATION_MODULE_ID",
    "MATERIAL_CHARACTERIZATION_STAGE_NUMBER",
    "execute_material_characterization",
    "SECTION_COMPONENT_CHARACTERIZATION_MODULE_ID",
    "SECTION_COMPONENT_CHARACTERIZATION_STAGE_NUMBER",
    "execute_section_component_characterization",
    "PROJECT_OBJECTIVES_MODULE_ID",
    "PROJECT_OBJECTIVES_STAGE_NUMBER",
    "evaluate_project_objectives",
    "SITE_HAZARD_MODULE_ID",
    "SITE_HAZARD_STAGE_NUMBER",
    "execute_site_hazard",
]
