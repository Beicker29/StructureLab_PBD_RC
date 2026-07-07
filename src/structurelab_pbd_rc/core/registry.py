"""Small registry for future material, section, element and frame models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from structurelab_pbd_rc.core.exceptions import RegistryError


@dataclass
class ModelRegistry:
    """Register named model classes or callables.

    The registry keeps design flows decoupled from specific implementations. A
    future stage flow can ask for a model by name without duplicating the model
    logic inside the stage module.
    """

    _models: dict[str, Any] = field(default_factory=dict)

    def register(self, name: str, model: Any, *, overwrite: bool = False) -> Any:
        """Register a model and return it.

        Returning the model allows decorator-style use in later phases.
        """

        if not name or not isinstance(name, str):
            raise RegistryError("Model name must be a non-empty string.")
        if name in self._models and not overwrite:
            raise RegistryError(f"Model '{name}' is already registered.")
        self._models[name] = model
        return model

    def get(self, name: str) -> Any:
        """Return a registered model by name."""

        try:
            return self._models[name]
        except KeyError as exc:
            raise RegistryError(f"Model '{name}' is not registered.") from exc

    def list_models(self) -> list[str]:
        """Return registered model names in sorted order."""

        return sorted(self._models)

    def clear(self) -> None:
        """Remove all registered models."""

        self._models.clear()
