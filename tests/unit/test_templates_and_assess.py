"""Unit and property tests for S2.T1 (paper templates) and S2.T2 (scale + legibility assessment)."""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from shapely.geometry import Polygon, box

from maps4u.layout.templates import (
    PaperTemplate,
    get_template,
    load_paper_templates,
)
from maps4u.render.assess import REMEDIATION_CHOICES, StyleSpec, assess

PILOT_GEOFENCES: dict[str, Polygon] = {
    "maroochydore": box(153.085, -26.660, 153.105, -26.645),
    "noosa": box(153.080, -26.398, 153.100, -26.383),
    "bribie_sandstone": box(153.140, -27.082, 153.162, -27.066),
}

ALL_PAPER_ORIENTATIONS: list[tuple[str, str]] = [
    ("A3", "landscape"),
    ("A3", "portrait"),
    ("A4", "landscape"),
    ("A4", "portrait"),
    ("A5", "landscape"),
    ("A5", "portrait"),
]


def test_all_six_paper_templates_resolve_valid_map_area() -> None:
    templates = load_paper_templates()
    assert set(templates.keys()) == {
        "A3-landscape",
        "A3-portrait",
        "A4-landscape",
        "A4-portrait",
        "A5-landscape",
        "A5-portrait",
    }
    for key, tpl in templates.items():
        assert isinstance(tpl, PaperTemplate)
        assert tpl.map_area_mm.w > 0
        assert tpl.map_area_mm.h > 0

        inner_area = tpl.inner_frame_mm.area_mm2
        furniture_area = sum(r.area_mm2 for r in tpl.furniture.values())
        available_after_furniture = max(1.0, inner_area - furniture_area)

        # S2.T1 requirement: map_area_mm >= 60% of page minus furniture
        ratio = tpl.map_area_mm.area_mm2 / available_after_furniture
        assert ratio >= 0.60, f"{key} map_area ratio {ratio:.3f} < 0.60"

        # Ensure map_area_mm does not intersect any reserved furniture cell
        for furn_name, furn_rect in tpl.furniture.items():
            assert not tpl.map_area_mm.intersects(furn_rect), (
                f"{key} map_area_mm intersects furniture {furn_name}"
            )


def test_assess_known_extent_produces_expected_scale_denominator() -> None:
    tpl = get_template("A4", "landscape")
    poly = PILOT_GEOFENCES["maroochydore"]
    result = assess(poly, tpl, StyleSpec())

    assert result.viable is True
    assert result.working_crs_epsg == 32756  # UTM Zone 56S
    # ~2.0 km wide by ~1.66 km high on A4 landscape usable frame -> scale around 1:8,000 - 1:16,000
    assert 6000.0 <= result.scale_denominator <= 18000.0
    assert result.min_printed_mm >= 1.5
    assert result.blockers == []


def test_assess_undersized_font_config_is_blocked_with_remediation_choices() -> None:
    tpl = get_template("A4", "landscape")
    poly = PILOT_GEOFENCES["maroochydore"]
    bad_style = StyleSpec(
        min_font_mm=1.5,
        mandatory_font_sizes_mm={
            "suburb": 4.0,
            "arterial": 2.4,
            "collector": 1.8,
            "local": 1.2,  # below 1.5 mm hard floor
        },
    )
    result = assess(poly, tpl, bad_style)
    assert result.viable is False
    assert result.min_printed_mm == pytest.approx(1.2)
    assert any(b["code"] == "FONT_BELOW_MINIMUM" for b in result.blockers)
    assert set(result.choices) == set(REMEDIATION_CHOICES)


def test_assess_dense_synthetic_fixture_triggers_density_warning() -> None:
    tpl = get_template("A5", "portrait")
    poly = PILOT_GEOFENCES["maroochydore"]
    # High named feature count triggers density warning
    result = assess(poly, tpl, StyleSpec(), named_feature_count=180)
    assert result.label_density_ratio >= 0.85
    assert any(w["code"] == "HIGH_LABEL_DENSITY" for w in result.warnings)
    assert set(result.choices) == set(REMEDIATION_CHOICES)


@pytest.mark.parametrize("pilot_name", list(PILOT_GEOFENCES.keys()))
@pytest.mark.parametrize(("paper", "orientation"), ALL_PAPER_ORIENTATIONS)
def test_all_pilot_geofences_pass_across_all_paper_orientations(
    pilot_name: str,
    paper: str,
    orientation: str,
) -> None:
    tpl = get_template(paper, orientation)  # type: ignore[arg-type]
    poly = PILOT_GEOFENCES[pilot_name]
    result = assess(poly, tpl, StyleSpec())
    assert result.viable is True, f"{pilot_name} failed on {paper}-{orientation}: {result.blockers}"
    assert result.scale_denominator > 0
    assert result.min_printed_mm >= 1.5


def test_scale_monotonicity_with_geofence_area() -> None:
    tpl = get_template("A4", "landscape")
    style = StyleSpec()
    small = box(153.090, -26.655, 153.095, -26.650)
    medium = box(153.085, -26.660, 153.100, -26.645)
    large = box(153.080, -26.665, 153.110, -26.640)

    r_small = assess(small, tpl, style)
    r_medium = assess(medium, tpl, style)
    r_large = assess(large, tpl, style)

    assert r_small.natural_scale_denominator < r_medium.natural_scale_denominator
    assert r_medium.natural_scale_denominator < r_large.natural_scale_denominator
    assert r_small.scale_denominator <= r_medium.scale_denominator <= r_large.scale_denominator


@settings(max_examples=25, deadline=None)
@given(
    half_deg_small=st.floats(min_value=0.002, max_value=0.015, allow_nan=False, allow_infinity=False),
    delta_deg=st.floats(min_value=0.002, max_value=0.025, allow_nan=False, allow_infinity=False),
)
def test_hypothesis_scale_monotonicity_with_area(half_deg_small: float, delta_deg: float) -> None:
    tpl = get_template("A4", "landscape")
    style = StyleSpec()
    cx, cy = 153.095, -26.652
    half_deg_large = half_deg_small + delta_deg

    poly_small = box(cx - half_deg_small, cy - half_deg_small, cx + half_deg_small, cy + half_deg_small)
    poly_large = box(cx - half_deg_large, cy - half_deg_large, cx + half_deg_large, cy + half_deg_large)

    r_small = assess(poly_small, tpl, style)
    r_large = assess(poly_large, tpl, style)

    assert r_small.area_km2 < r_large.area_km2
    assert r_small.natural_scale_denominator < r_large.natural_scale_denominator
    assert r_small.scale_denominator <= r_large.scale_denominator
