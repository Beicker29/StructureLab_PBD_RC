"""V2 workflow infrastructure; V1 stage interfaces remain unchanged."""

from structurelab_pbd_rc.workflow.catalog import (
    DEFAULT_CATALOG,
    DEFAULT_MODULES,
    ModuleCatalog,
    ModuleDefinition,
)
from structurelab_pbd_rc.workflow.context import RunContext

__all__ = [
    "DEFAULT_CATALOG",
    "DEFAULT_MODULES",
    "HandlerOutput",
    "HandlerRegistration",
    "HandlerRegistry",
    "ModuleCatalog",
    "ModuleDefinition",
    "PlanEntry",
    "PlanStatus",
    "RunContext",
    "StageExecutionRequest",
    "WorkflowDAG",
    "WorkflowPlan",
    "WorkflowRunResult",
    "WorkflowRunner",
    "default_handler_registry",
    "PublishedRunIndex",
    "PublishedRunReference",
    "ReuseSelection",
]


def __getattr__(name: str) -> object:
    """Load runner exports lazily so artifact publication can import RunContext."""

    registry_exports = {
        "HandlerOutput",
        "HandlerRegistration",
        "HandlerRegistry",
        "StageExecutionRequest",
        "default_handler_registry",
    }
    runner_exports = {
        "PlanEntry",
        "PlanStatus",
        "WorkflowDAG",
        "WorkflowPlan",
        "WorkflowRunResult",
        "WorkflowRunner",
    }
    reuse_exports = {
        "PublishedRunIndex",
        "PublishedRunReference",
        "ReuseSelection",
    }
    if name in registry_exports:
        from structurelab_pbd_rc.workflow import registry

        return getattr(registry, name)
    if name in runner_exports:
        from structurelab_pbd_rc.workflow import runner

        return getattr(runner, name)
    if name in reuse_exports:
        from structurelab_pbd_rc.workflow import reuse

        return getattr(reuse, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

