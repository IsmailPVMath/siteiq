"""Tests for LayoutIQ GCR / pitch strategy."""

from pvmath_workflow.gcr_strategy import (
    infer_land_cost,
    pitch_from_gcr,
    pitch_sweep_values,
    recommended_gcr,
)


def test_balanced_defaults_match_industry_table():
    assert recommended_gcr("FT_1P", mode="balanced") == 0.45
    assert recommended_gcr("FT_2P", mode="balanced") == 0.47
    assert recommended_gcr("FT_3P", mode="balanced") == 0.50
    assert recommended_gcr("FT_4P", mode="balanced") == 0.52
    assert recommended_gcr("SAT_1P", mode="balanced") == 0.33
    assert recommended_gcr("SAT_2P", mode="balanced") == 0.35


def test_land_cost_inference():
    assert infer_land_cost("Germany") == "expensive"
    assert infer_land_cost("Texas, USA") == "cheap"
    assert infer_land_cost("Rajasthan, India") == "cheap"


def test_high_energy_lower_than_balanced():
    row_ns = 2.094
    balanced = recommended_gcr("FT_1P", mode="balanced")
    high = recommended_gcr("FT_1P", mode="high_energy", land_cost="cheap")
    assert high < balanced
    assert pitch_from_gcr(row_ns, high) > pitch_from_gcr(row_ns, balanced)


def test_land_optimized_higher_than_balanced():
    balanced = recommended_gcr("SAT_1P", mode="balanced")
    land = recommended_gcr("SAT_1P", mode="land_optimized", land_cost="expensive")
    assert land > balanced


def test_pitch_sweep_within_practical_band():
    row_ns = 2.094 * 2
    pitches, guidance = pitch_sweep_values("FT_2P", row_ns, mode="balanced")
    assert pitches
    assert guidance["recommended_pitch_m"] >= guidance["pitch_m_min"]
    assert all(p > row_ns for p in pitches)
