"""Canonical V2 module catalog with semantic IDs and visible numbers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from structurelab_pbd_rc.contracts._common import (
    ensure_unique_ids,
    validate_identifier,
    validate_schema_version,
)
from structurelab_pbd_rc.contracts._module_identity import V2_MODULE_IDENTITIES
from structurelab_pbd_rc.core.exceptions import ContractError, DependencyError


@dataclass(frozen=True)
class ModuleDefinition:
    stage_number: str
    module_id: str
    name: str
    dependencies: tuple[str, ...] = ()
    conditional_dependencies: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "dependencies", tuple(self.dependencies))
        object.__setattr__(self, "conditional_dependencies", tuple(self.conditional_dependencies))
        if (
            len(self.stage_number) != 2
            or not self.stage_number.isdigit()
            or not 0 <= int(self.stage_number) <= 12
        ):
            raise ContractError("stage_number must be a two-digit value from '00' to '12'.")
        validate_identifier(self.module_id, name="module_id", semantic=True)
        if not isinstance(self.name, str) or not self.name.strip():
            raise ContractError("module name must be a non-empty string.")
        for dependency in self.dependencies + self.conditional_dependencies:
            validate_identifier(dependency, name="module dependency", semantic=True)
        ensure_unique_ids(self.dependencies, name="required module dependency")
        ensure_unique_ids(self.conditional_dependencies, name="conditional module dependency")
        overlap = set(self.dependencies) & set(self.conditional_dependencies)
        if overlap:
            raise ContractError(
                f"Dependencies cannot be both required and conditional: {', '.join(sorted(overlap))}."
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "stage_number": self.stage_number,
            "module_id": self.module_id,
            "name": self.name,
            "dependencies": list(self.dependencies),
            "conditional_dependencies": list(self.conditional_dependencies),
        }


class ModuleCatalog:
    """Validated lookup table; numeric V1 stage aliases are never resolved."""

    def __init__(self, modules: Iterable[ModuleDefinition], *, schema_version: str = "2") -> None:
        self.schema_version = validate_schema_version(schema_version)
        self.modules = tuple(modules)
        if not self.modules:
            raise ContractError("ModuleCatalog cannot be empty.")
        ensure_unique_ids((item.module_id for item in self.modules), name="module_id")
        ensure_unique_ids((item.stage_number for item in self.modules), name="stage_number")
        known = {item.module_id for item in self.modules}
        for module in self.modules:
            for dependency in module.dependencies + module.conditional_dependencies:
                if dependency not in known:
                    raise DependencyError(
                        f"Module {module.module_id!r} references unknown dependency {dependency!r}."
                    )
                if dependency == module.module_id:
                    raise DependencyError(f"Module {module.module_id!r} cannot depend on itself.")
        self._by_id = {item.module_id: item for item in self.modules}
        self._by_number = {item.stage_number: item for item in self.modules}

    def by_id(self, module_id: str) -> ModuleDefinition:
        try:
            return self._by_id[module_id]
        except KeyError as exc:
            raise ContractError(f"Unknown V2 module_id {module_id!r}.") from exc

    def by_number(self, stage_number: str) -> ModuleDefinition:
        try:
            return self._by_number[stage_number]
        except KeyError as exc:
            raise ContractError(f"Unknown V2 stage_number {stage_number!r}.") from exc

    def resolve(self, reference: str) -> ModuleDefinition:
        """Resolve only semantic IDs or bare 00-12 numbers.

        ``stage_02`` and ``stage_03`` are deliberately rejected because those
        names carry V1 meanings that differ from V2 visible numbering.
        """

        if reference.startswith("stage_"):
            raise ContractError(
                f"Legacy reference {reference!r} is ambiguous in V2; use a semantic "
                "module_id or a bare two-digit stage_number."
            )
        if reference in self._by_id:
            return self._by_id[reference]
        if reference in self._by_number:
            return self._by_number[reference]
        raise ContractError(f"Unknown V2 module reference {reference!r}.")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "modules": [item.to_dict() for item in self.modules],
        }


_DEPENDENCIES: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "project_objectives": ((), ()),
    "site_hazard": (("project_objectives",), ()),
    "baseline_model": (("project_objectives",), ("site_hazard",)),
    "material_characterization": (("project_objectives",), ("baseline_model",)),
    "section_component_characterization": (
        ("project_objectives",),
        ("baseline_model", "material_characterization"),
    ),
    "ground_motion": (("project_objectives", "site_hazard"), ("baseline_model",)),
    "nonlinear_model": (
        (
            "project_objectives", "baseline_model", "material_characterization",
            "section_component_characterization",
        ),
        (),
    ),
    "nonlinear_analysis": (("nonlinear_model",), ("ground_motion",)),
    "demand_performance": (
        ("project_objectives", "section_component_characterization", "nonlinear_analysis"),
        (),
    ),
    "collapse_fragility": (
        ("project_objectives", "ground_motion", "nonlinear_analysis", "demand_performance"),
        (),
    ),
    "damage_loss": (("baseline_model", "demand_performance"), ("collapse_fragility",)),
    "seismic_risk": (("project_objectives", "site_hazard"), ("collapse_fragility", "damage_loss")),
    "reporting_iteration": (
        ("project_objectives",),
        tuple(item[1] for item in V2_MODULE_IDENTITIES[1:12]),
    ),
}


DEFAULT_MODULES = tuple(
    ModuleDefinition(
        stage_number=number,
        module_id=module_id,
        name=name,
        dependencies=_DEPENDENCIES[module_id][0],
        conditional_dependencies=_DEPENDENCIES[module_id][1],
    )
    for number, module_id, name in V2_MODULE_IDENTITIES
)

DEFAULT_CATALOG = ModuleCatalog(DEFAULT_MODULES)

