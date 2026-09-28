"""In-memory V2 service over the unchanged seismic spectra kernel."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from types import MappingProxyType
from typing import Any, Mapping

from structurelab_pbd_rc.contracts import (
    BoundaryDefinition,
    PhysicalQuantity,
    ReferenceSystem,
    SignConvention,
)
from structurelab_pbd_rc.contracts._common import copy_json_mapping
from structurelab_pbd_rc.mechanics.hazard.seismic.spectra import (
    CCP14SpectrumParameters,
    ccp14_spectral_acceleration,
    ccp14_spectrum,
    ccp14_transition_parameters,
    generate_period_vector,
    nsr10_spectrum,
    nsr10_transition_parameters,
)


LEVEL_KEYS = ("service", "design", "maximum_considered")
EXPECTED_RETURN_PERIODS = (31, 475, 2500)


def _float(value: Any, *, name: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid numeric value for {name}: {value!r}") from exc


def _integer(value: Any, *, name: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid integer value for {name}: {value!r}") from exc


def _require_mapping(value: Any, *, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be a mapping.")
    return value


@dataclass(frozen=True)
class HazardSpectraInput:
    """Structured native inputs accepted by the in-memory hazard service."""

    case_id: str
    title: str
    units: Mapping[str, str]
    seismic: Mapping[str, Any]

    def __post_init__(self) -> None:
        if self.case_id not in {"case_01_nsr10", "case_02_sgc_ccp14"}:
            raise ValueError(f"Unsupported hazard spectrum case_id: {self.case_id!r}.")
        if not isinstance(self.title, str) or not self.title.strip():
            raise ValueError("Hazard spectrum title must be non-empty.")
        units = dict(self.units)
        if units != {"period": "s", "spectral_acceleration": "g"}:
            raise ValueError("Hazard spectra require native units period=s and acceleration=g.")
        object.__setattr__(self, "units", MappingProxyType(units))
        object.__setattr__(
            self,
            "seismic",
            MappingProxyType(copy_json_mapping(self.seismic, name="hazard.seismic")),
        )

    @classmethod
    def from_stage_01_mapping(cls, data: Mapping[str, Any]) -> "HazardSpectraInput":
        config = _require_mapping(data, name="hazard configuration")
        if config.get("stage_id") != "stage_01":
            raise ValueError("Hazard configuration stage_id must remain 'stage_01'.")
        hazard = _require_mapping(config.get("hazard"), name="hazard")
        return cls(
            case_id=str(config.get("case_id", "")),
            title=str(config.get("title", "")),
            units=_require_mapping(config.get("units"), name="units"),
            seismic=_require_mapping(hazard.get("seismic"), name="hazard.seismic"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "title": self.title,
            "units": dict(self.units),
            "seismic": copy_json_mapping(self.seismic, name="hazard.seismic"),
        }


@dataclass(frozen=True)
class HazardSpectraResult:
    """Scientific result retained in memory, independent of publication format."""

    case_id: str
    title: str
    periods: tuple[float, ...]
    spectrum_rows: tuple[Mapping[str, Any], ...]
    parameter_rows: tuple[Mapping[str, Any], ...]
    transition_parameters: Any
    level_columns: Mapping[str, str]
    source_metadata: Mapping[str, Any]
    period_boundary: BoundaryDefinition
    acceleration_boundary: BoundaryDefinition

    def __post_init__(self) -> None:
        object.__setattr__(self, "periods", tuple(self.periods))
        object.__setattr__(
            self,
            "spectrum_rows",
            tuple(MappingProxyType(dict(row)) for row in self.spectrum_rows),
        )
        object.__setattr__(
            self,
            "parameter_rows",
            tuple(MappingProxyType(dict(row)) for row in self.parameter_rows),
        )
        object.__setattr__(self, "level_columns", MappingProxyType(dict(self.level_columns)))
        object.__setattr__(
            self,
            "source_metadata",
            MappingProxyType(copy_json_mapping(self.source_metadata, name="source_metadata")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "2",
            "module_id": "site_hazard",
            "case_id": self.case_id,
            "title": self.title,
            "periods": list(self.periods),
            "spectrum_rows": [dict(row) for row in self.spectrum_rows],
            "parameter_rows": [dict(row) for row in self.parameter_rows],
            "transition_parameters": self.transition_parameters,
            "level_columns": dict(self.level_columns),
            "source_metadata": dict(self.source_metadata),
            "boundaries": {
                "period": self.period_boundary.to_dict(),
                "spectral_acceleration": self.acceleration_boundary.to_dict(),
            },
        }


def _periods(seismic: Mapping[str, Any]) -> tuple[float, ...]:
    period_range = _require_mapping(seismic.get("period_range"), name="period_range")
    return tuple(
        generate_period_vector(
            _float(period_range.get("start"), name="period_range.start"),
            _float(period_range.get("end"), name="period_range.end"),
            _float(period_range.get("step"), name="period_range.step"),
        )
    )


def _validate_levels(seismic: Mapping[str, Any]) -> Mapping[str, Any]:
    levels = _require_mapping(seismic.get("hazard_levels"), name="hazard_levels")
    if any(key not in levels for key in LEVEL_KEYS):
        raise ValueError("Hazard levels service, design and maximum_considered are required.")
    periods = tuple(
        _integer(
            _require_mapping(levels[key], name=f"hazard_levels.{key}").get(
                "return_period_years"
            ),
            name=f"hazard_levels.{key}.return_period_years",
        )
        for key in LEVEL_KEYS
    )
    if periods != EXPECTED_RETURN_PERIODS:
        raise ValueError("Return periods must be ordered as 31, 475 and 2500 years.")
    return levels


def _nsr10_result(inputs: HazardSpectraInput) -> tuple[
    tuple[float, ...],
    tuple[dict[str, Any], ...],
    tuple[dict[str, Any], ...],
    dict[str, Any],
    dict[str, str],
]:
    seismic = inputs.seismic
    periods = _periods(seismic)
    levels = _validate_levels(seismic)
    raw = _require_mapping(seismic.get("nsr10_parameters"), name="nsr10_parameters")
    parameters = nsr10_transition_parameters(
        Aa=_float(raw.get("Aa"), name="Aa"),
        Av=_float(raw.get("Av"), name="Av"),
        Fa=_float(raw.get("Fa"), name="Fa"),
        Fv=_float(raw.get("Fv"), name="Fv"),
        importance_factor=_float(raw.get("importance_factor"), name="importance_factor"),
    )
    base = nsr10_spectrum(periods, parameters)
    factors = {
        key: _float(
            _require_mapping(levels[key], name=f"hazard_levels.{key}").get("scale_factor"),
            name=f"hazard_levels.{key}.scale_factor",
        )
        for key in LEVEL_KEYS
    }
    if any(value <= 0 for value in factors.values()):
        raise ValueError("NSR-10 hazard-level scale factors must be positive.")
    columns = {
        "service": "Sa_servicio_31",
        "design": "Sa_diseno_475",
        "maximum_considered": "Sa_maximo_considerado_2500",
    }
    rows = tuple(
        {
            "period_s": period,
            columns["service"]: factors["service"] * value,
            columns["design"]: factors["design"] * value,
            columns["maximum_considered"]: factors["maximum_considered"] * value,
        }
        for period, value in zip(periods, base)
    )
    parameter_rows = (
        {"parameter": "Aa", "value": parameters.Aa, "unit": "g", "equation": "input"},
        {"parameter": "Av", "value": parameters.Av, "unit": "g", "equation": "input"},
        {"parameter": "Fa", "value": parameters.Fa, "unit": "-", "equation": "input"},
        {"parameter": "Fv", "value": parameters.Fv, "unit": "-", "equation": "input"},
        {
            "parameter": "I",
            "value": parameters.importance_factor,
            "unit": "-",
            "equation": "input",
        },
        {
            "parameter": "T0",
            "value": parameters.T0,
            "unit": "s",
            "equation": "0.1 * Av * Fv / (Aa * Fa)",
        },
        {
            "parameter": "Tc",
            "value": parameters.Tc,
            "unit": "s",
            "equation": "0.48 * Av * Fv / (Aa * Fa)",
        },
        {"parameter": "TL", "value": parameters.TL, "unit": "s", "equation": "2.4 * Fv"},
        {
            "parameter": "Sa_plateau",
            "value": parameters.Sa_plateau,
            "unit": "g",
            "equation": "2.5 * Aa * Fa * I",
        },
        {
            "parameter": "F_31",
            "value": levels["service"]["scale_factor"],
            "unit": "-",
            "equation": "Sa_31(T) = F_31 * Sa_475(T)",
        },
        {
            "parameter": "F_2500",
            "value": levels["maximum_considered"]["scale_factor"],
            "unit": "-",
            "equation": "Sa_2500(T) = F_2500 * Sa_475(T)",
        },
    )
    return periods, rows, parameter_rows, asdict(parameters), columns


def _ccp14_parameter_row(parameters: CCP14SpectrumParameters) -> dict[str, Any]:
    return {
        "return_period_years": parameters.return_period_years,
        "PGA": parameters.PGA,
        "Sa_0_2": parameters.Ss,
        "Sa_1_0": parameters.S1,
        "Fpga": parameters.Fpga,
        "Fa": parameters.Fa,
        "Fv": parameters.Fv,
        "As": parameters.As,
        "SDS": parameters.SDS,
        "SD1": parameters.SD1,
        "T0": parameters.T0,
        "Ts": parameters.Ts,
        "Sa_at_T_0": ccp14_spectral_acceleration(0.0, parameters),
        "Sa_at_T_0_2": ccp14_spectral_acceleration(0.2, parameters),
        "Sa_at_T_1_0": ccp14_spectral_acceleration(1.0, parameters),
        "units": "g, s",
        "source": "SGC hazard values with CCP-14 interpolated site factors",
    }


def _ccp14_result(inputs: HazardSpectraInput) -> tuple[
    tuple[float, ...],
    tuple[dict[str, Any], ...],
    tuple[dict[str, Any], ...],
    list[dict[str, Any]],
    dict[str, str],
]:
    seismic = inputs.seismic
    periods = _periods(seismic)
    levels = _validate_levels(seismic)
    site = _require_mapping(seismic.get("site"), name="site")
    profile = str(site.get("profile", ""))
    parameters = tuple(
        ccp14_transition_parameters(
            return_period_years=_integer(levels[key]["return_period_years"], name="return_period"),
            PGA=_float(levels[key].get("PGA"), name=f"{key}.PGA"),
            Ss=_float(levels[key].get("Sa_0_2"), name=f"{key}.Sa_0_2"),
            S1=_float(levels[key].get("Sa_1_0"), name=f"{key}.Sa_1_0"),
            site_profile=profile,
        )
        for key in LEVEL_KEYS
    )
    spectra = {
        item.return_period_years: ccp14_spectrum(periods, item) for item in parameters
    }
    columns = {
        "service": "Sa_SGC_CCP14_31",
        "design": "Sa_SGC_CCP14_475",
        "maximum_considered": "Sa_SGC_CCP14_2500",
    }
    rows = tuple(
        {
            "period_s": period,
            columns["service"]: spectra[31][index],
            columns["design"]: spectra[475][index],
            columns["maximum_considered"]: spectra[2500][index],
        }
        for index, period in enumerate(periods)
    )
    return (
        periods,
        rows,
        tuple(_ccp14_parameter_row(item) for item in parameters),
        [asdict(item) for item in parameters],
        columns,
    )


def compute_hazard_spectra(inputs: HazardSpectraInput) -> HazardSpectraResult:
    """Invoke only existing NSR-10/CCP-14 kernels and retain results in memory."""

    if not isinstance(inputs, HazardSpectraInput):
        raise TypeError("inputs must be a HazardSpectraInput instance.")
    if inputs.case_id == "case_01_nsr10":
        periods, rows, parameter_rows, transitions, columns = _nsr10_result(inputs)
        source_type = "normative_nsr10"
    else:
        periods, rows, parameter_rows, transitions, columns = _ccp14_result(inputs)
        source_type = "sgc_values_with_normative_ccp14_shape"
    return HazardSpectraResult(
        case_id=inputs.case_id,
        title=inputs.title,
        periods=periods,
        spectrum_rows=rows,
        parameter_rows=parameter_rows,
        transition_parameters=transitions,
        level_columns=columns,
        source_metadata={
            "source_type": source_type,
            "probabilistic_hazard_result": False,
            "exceedance_curve_available": False,
            "native_units": {"period": "s", "spectral_acceleration": "g"},
            "sign_convention": "unsigned_nonnegative",
            "source": dict(inputs.seismic.get("source", {})),
        },
        period_boundary=BoundaryDefinition(
            PhysicalQuantity.TIME,
            "s",
            SignConvention.UNSIGNED_NONNEGATIVE,
            ReferenceSystem.SCALAR,
        ),
        acceleration_boundary=BoundaryDefinition(
            PhysicalQuantity.ACCELERATION,
            "g",
            SignConvention.UNSIGNED_NONNEGATIVE,
            ReferenceSystem.SCALAR,
        ),
    )
