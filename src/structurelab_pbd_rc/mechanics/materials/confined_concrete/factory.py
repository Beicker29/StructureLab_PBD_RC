"""Model selection for confined concrete."""

from __future__ import annotations

from typing import Any, Callable, Mapping

from structurelab_pbd_rc.core.exceptions import ConfigError
from structurelab_pbd_rc.core.validation import require_keys
from structurelab_pbd_rc.mechanics.materials.confined_concrete.monotonic.mander_1988 import (
    Mander1988MonotonicConfinedConcrete,
)


ModelBuilder = Callable[[Mapping[str, Any]], Any]

MODEL_BUILDERS: dict[tuple[str, str], ModelBuilder] = {
    (
        "monotonic",
        Mander1988MonotonicConfinedConcrete.model_id,
    ): Mander1988MonotonicConfinedConcrete.from_config,
}


def build_confined_concrete_model(config: Mapping[str, Any]) -> Any:
    """Construct a configured confined-concrete model."""

    require_keys(config, ("analysis_type", "model"), context="material model")
    key = (str(config["analysis_type"]), str(config["model"]))
    try:
        builder = MODEL_BUILDERS[key]
    except KeyError as exc:
        available = ", ".join(
            f"{analysis}/{model}"
            for analysis, model in sorted(MODEL_BUILDERS)
        )
        raise ConfigError(
            f"Unsupported confined concrete model {key!r}. "
            f"Available: {available}"
        ) from exc
    return builder(config)
