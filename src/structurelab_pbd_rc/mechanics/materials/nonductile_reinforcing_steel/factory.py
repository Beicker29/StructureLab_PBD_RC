"""Central model selection for nonductile reinforcing steel."""

from __future__ import annotations

from typing import Any, Callable, Mapping

from structurelab_pbd_rc.core.exceptions import ConfigError
from structurelab_pbd_rc.core.validation import require_keys
from structurelab_pbd_rc.mechanics.materials.nonductile_reinforcing_steel.cyclic.menegotto_pinto import (
    MenegottoPinto,
)
from structurelab_pbd_rc.mechanics.materials.nonductile_reinforcing_steel.monotonic.modified_ramberg_osgood import (
    ModifiedRambergOsgood,
)


ModelBuilder = Callable[[Mapping[str, Any]], Any]

MODEL_BUILDERS: dict[tuple[str, str], ModelBuilder] = {
    ("monotonic", ModifiedRambergOsgood.model_id): ModifiedRambergOsgood.from_config,
    ("cyclic", MenegottoPinto.model_id): MenegottoPinto.from_config,
}


def build_nonductile_steel_model(config: Mapping[str, Any]) -> Any:
    """Construct a configured model without distributed model-name branches."""

    require_keys(config, ("analysis_type", "model"), context="material model")
    key = (str(config["analysis_type"]), str(config["model"]))
    try:
        builder = MODEL_BUILDERS[key]
    except KeyError as exc:
        available = ", ".join(f"{analysis}/{model}" for analysis, model in sorted(MODEL_BUILDERS))
        raise ConfigError(f"Unsupported nonductile steel model {key!r}. Available: {available}") from exc
    return builder(config)
