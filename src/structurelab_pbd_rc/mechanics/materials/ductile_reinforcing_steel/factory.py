"""Model selection for ductile reinforcing steel."""

from __future__ import annotations

from typing import Any, Callable, Mapping

from structurelab_pbd_rc.core.exceptions import ConfigError
from structurelab_pbd_rc.core.validation import require_keys
from structurelab_pbd_rc.mechanics.materials.ductile_reinforcing_steel.monotonic.rdm_2019 import (
    RDM2019MonotonicCompressionModel,
)


ModelBuilder = Callable[[Mapping[str, Any]], Any]

MODEL_BUILDERS: dict[tuple[str, str], ModelBuilder] = {
    (
        "monotonic",
        RDM2019MonotonicCompressionModel.model_id,
    ): RDM2019MonotonicCompressionModel.from_config,
}


def build_ductile_steel_model(config: Mapping[str, Any]) -> Any:
    """Construct a configured ductile-steel model."""

    require_keys(config, ("analysis_type", "model"), context="material model")
    key = (str(config["analysis_type"]), str(config["model"]))
    try:
        builder = MODEL_BUILDERS[key]
    except KeyError as exc:
        available = ", ".join(f"{analysis}/{model}" for analysis, model in sorted(MODEL_BUILDERS))
        raise ConfigError(f"Unsupported ductile steel model {key!r}. Available: {available}") from exc
    return builder(config)
