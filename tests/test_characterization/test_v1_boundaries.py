"""V1 edge behavior recorded before changing algorithms or validation."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from zipfile import ZipFile

import pytest
import yaml

from structurelab_pbd_rc.core.exceptions import ConfigError, MaterialDomainError
from structurelab_pbd_rc.design.stages.stage_02_input_config import (
    _validate_identifier, _validate_identifiers_and_routes, load_enabled_stage_02_inputs,
)
from structurelab_pbd_rc.design.stages.stage_03_section_characterization import _safe_sheet_folder_name, run as run_sections
from structurelab_pbd_rc.io.read_xlsx import list_xlsx_sheets, read_xlsx_rows, read_xlsx_table
from structurelab_pbd_rc.mechanics.idealization.energy_equivalent import (
    BackbonePoint as P, EnergyEquivalentSettings as S,
    bilinearize_energy_equivalent as bilinear, clean_positive_backbone as clean,
)
from structurelab_pbd_rc.mechanics.materials.nonductile_reinforcing_steel.cyclic.menegotto_pinto import MenegottoPinto
from structurelab_pbd_rc.mechanics.materials.confined_concrete.monotonic.mander_1988 import Mander1988MonotonicConfinedConcrete
from structurelab_pbd_rc.mechanics.materials.ductile_reinforcing_steel.monotonic.rdm_2019 import RDM2019SectionModelSet
from structurelab_pbd_rc.mechanics.materials.nonductile_reinforcing_steel.monotonic.modified_ramberg_osgood import ModifiedRambergOsgood


ROOT = Path(__file__).resolve().parents[2]


def test_energy_cleaning_origin_duplicate_sign_and_nonfinite() -> None:
    points = clean([P(-2, -4), P(1, 2), P(1, 3), P(float("nan"), 9), P(4, float("inf"))])
    assert points == [P(0, 0), P(1, 3), P(2, 4)]
    assert clean([P(0, 4), P(1, 2)])[0] == P(0, 0)
    with pytest.raises(ValueError, match="no valid numeric"):
        clean([P(float("nan"), 1), P(1, float("inf"))])


def test_energy_zero_area_and_no_candidate_are_rejected() -> None:
    with pytest.raises(ValueError, match="Area under"):
        bilinear([P(0, 0), P(1, 0)])
    with pytest.raises(ValueError, match="No valid"):
        bilinear([P(0, 0), P(1, 1)], deformation_u=0.01, settings=S(search_points=30))


@pytest.mark.parametrize("response", [[0, 3, 2], [0, 3, 3]])
def test_energy_softening_and_plateau(response: list[int]) -> None:
    result = bilinear([P(i, value) for i, value in enumerate(response)], settings=S(search_points=100))
    assert result["peak"]["response"] == 3
    assert result["area"]["actual"] > 0
    assert result["status"] in {"converged", "best_effort"}


def test_energy_best_effort_does_not_raise() -> None:
    result = bilinear([P(0, 0), P(1, 2), P(2, 3), P(3, 1)], settings=S(tolerance=0, search_points=17))
    assert result["status"] == "best_effort"
    assert result["parameters"]["absolute_relative_error"] > 0


def _independent_workbook(path: Path) -> None:
    """Hand-authored OOXML; intentionally does not use the project XLSX writer."""
    namespace = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    workbook = f'<workbook xmlns="{namespace}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Boundary" sheetId="1" r:id="rId1"/></sheets></workbook>'
    rels = '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Target="worksheets/sheet1.xml" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"/></Relationships>'
    shared = f'<sst xmlns="{namespace}"><si><t>shared</t></si></sst>'
    sheet = f'''<worksheet xmlns="{namespace}"><sheetData>
      <row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="inlineStr"><is><t>inline</t></is></c><c r="AA1"><v>42</v></c></row>
      <row r="2"><c r="A2"/><c r="AA2"><f>40+2</f><v>42</v></c></row>
    </sheetData></worksheet>'''
    with ZipFile(path, "w") as archive:
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", rels)
        archive.writestr("xl/sharedStrings.xml", shared)
        archive.writestr("xl/worksheets/sheet1.xml", sheet)


def test_independent_xlsx_variants(tmp_path: Path) -> None:
    path = tmp_path / "independent.xlsx"
    _independent_workbook(path)
    assert list_xlsx_sheets(path) == ["Boundary"]
    rows = read_xlsx_rows(path)
    assert rows == [
        {"__row_number__": 1, "A": "shared", "B": "inline", "AA": 42},
        {"__row_number__": 2, "A": None, "AA": 42},
    ]
    assert read_xlsx_table(path) == [["shared", "inline", 42], [None, None, 42]]
    with pytest.raises(ConfigError, match="not found"):
        read_xlsx_rows(path, sheet_name="Absent")


@pytest.mark.parametrize("value", ["../escape", "a/b", "a\\b", "", "bad space", ".hidden"])
def test_stage02_rejects_unsafe_identifiers(value: str) -> None:
    with pytest.raises(ConfigError, match="must match"):
        _validate_identifier(value, name="case_id")


def test_stage02_rejects_case_insensitive_model_definition() -> None:
    original = next(item for item in load_enabled_stage_02_inputs(ROOT / "configs/stage_02") if item.model_id == "Mon_MRO")
    duplicate = replace(original, model_id="mon_mro", source_path=Path("other-input.json"))
    with pytest.raises(ConfigError, match="Only one JSON"):
        _validate_identifiers_and_routes([original, duplicate])


def test_sheet_sanitization_can_collide() -> None:
    assert _safe_sheet_folder_name("A/B") == "A_B"
    assert _safe_sheet_folder_name("A:B") == "A_B"
    assert _safe_sheet_folder_name("... ") == "sheet"
    assert _safe_sheet_folder_name("CON") == "CON"  # Windows device name is not rejected


def test_stage03_rejects_traversal_only_after_creating_directory(tmp_path: Path) -> None:
    config = yaml.safe_load((ROOT / "configs/stage_03/section_characterization.yaml").read_text(encoding="utf-8"))
    config["stage_id"] = "../escaped"
    config["source"]["workbook"] = str((ROOT / config["source"]["workbook"]).resolve())
    path = tmp_path / "bad_stage.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    with pytest.raises(ValueError, match="Refusing to reset"):
        run_sections(path, tmp_path / "out")
    assert (tmp_path / "escaped/data").is_dir()


def test_cyclic_repeated_history_and_independent_instances() -> None:
    source = json.loads((ROOT / "configs/stage_02/nonductile_reinforcing_steel/cyclic/Cyc_MP.json").read_text(encoding="utf-8"))
    config = source["inputs"]
    first = MenegottoPinto.from_config(config)
    second = MenegottoPinto.from_config(config)
    history = [0.0, 0.001, 0.001, -0.002, 0.0]
    first_responses = first.evaluate_history(history)
    second_responses = second.evaluate_history(history)
    assert [r.strain for r in first_responses] == history
    assert [r.stress_mpa for r in first_responses] == pytest.approx([r.stress_mpa for r in second_responses])
    first.set_trial_strain(0.003)
    assert first.revert_to_last_commit().strain == history[-1]
    assert second.committed_state.strain == history[-1]
    first.reset()
    assert first.committed_state.strain == 0.0
    assert second.committed_state.strain == history[-1]


def test_material_signs_units_and_domain_edges_from_canonical_inputs() -> None:
    folder = ROOT / "configs/stage_02"
    def inputs(relative: str) -> dict[str, object]:
        return json.loads((folder / relative).read_text(encoding="utf-8"))["inputs"]
    concrete = Mander1988MonotonicConfinedConcrete.from_config(inputs("confined_concrete/monotonic/Mon_Mander1988.json"))
    steel = RDM2019SectionModelSet.from_config(inputs("ductile_reinforcing_steel/monotonic/Mon_RDM2019.json")).models["bending"]
    mesh = ModifiedRambergOsgood.from_config(inputs("nonductile_reinforcing_steel/monotonic/Mon_MRO.json"))
    assert concrete.response(concrete.peak_confined_strain).stress_mpa > 0
    assert concrete.tension_response(-concrete.tensile_ultimate_strain).stress_mpa < 0
    assert concrete.response(concrete.ultimate_strain * 1.01).failed
    assert steel.response(0.001).stress_mpa > 0
    assert steel.tension_response(0.001).stress_mpa > 0
    assert steel.response(steel.parameters.epsilon_su * 1.01).in_domain is False
    assert mesh.response(0.001).stress_mpa > 0
    with pytest.raises(MaterialDomainError, match="compression is unsupported"):
        mesh.response(-0.001)
    with pytest.raises(MaterialDomainError, match="tensile strain"):
        mesh.response(mesh.parameters.ultimate_strain * 1.01)
