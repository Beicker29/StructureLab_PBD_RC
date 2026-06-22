"""Tests for reinforcing bar database."""

from structurelab_pbd_rc.mechanics.materials.library.rebar_database import get_rebar_properties, rebar_exists


def test_required_rebars_exist() -> None:
    assert rebar_exists("#4")
    assert rebar_exists("#7")
    assert get_rebar_properties("#4")["diameter_mm"] > 0
    assert get_rebar_properties("#7")["area_mm2"] > get_rebar_properties("#4")["area_mm2"]


