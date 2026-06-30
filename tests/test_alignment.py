"""Tests for alignment guide → layout azimuth."""

from layoutiq.alignment import (
    azimuth_from_alignment_polyline,
    bearing_to_layout_azimuth,
    layout_rotation_angle,
    resolve_layout_azimuth,
)
from layoutiq.engine import run_layout


def test_bearing_to_layout_azimuth_ns():
    assert bearing_to_layout_azimuth(0) == 180
    assert bearing_to_layout_azimuth(180) == 180


def test_bearing_to_layout_azimuth_ew():
    assert bearing_to_layout_azimuth(90) == 90
    assert bearing_to_layout_azimuth(270) == 270


def test_polyline_ns_gives_180():
    points = [(32.0, -96.5), (32.004, -96.5), (32.008, -96.5)]
    assert azimuth_from_alignment_polyline(points) == 180.0


def test_polyline_ew_gives_90():
    points = [(32.0, -96.5), (32.0, -96.496)]
    assert azimuth_from_alignment_polyline(points) == 90.0


def test_resolve_prefers_polyline():
    poly = [(32.0, -96.5), (32.0, -96.496)]
    assert resolve_layout_azimuth(180.0, poly) == 90.0


def test_sat_rotation_default_matches_legacy():
    assert layout_rotation_angle(180.0, is_tracker=True) == 90.0


def test_sat_azimuth_changes_module_count():
    ref_lat, ref_lon = 32.0, -96.5
    dlat, dlon = 0.004, 0.004
    ring = [
        (ref_lat, ref_lon),
        (ref_lat + dlat, ref_lon),
        (ref_lat + dlat, ref_lon + dlon),
        (ref_lat, ref_lon + dlon),
    ]
    ns = run_layout(
        ring,
        module_h=2.094,
        module_w=1.038,
        n_portrait=1,
        pitch=6.35,
        setback=5.0,
        azimuth=180.0,
        mounting_type="sat",
        modules_per_string=28,
        inter_string_gap_m=0.5,
        ref_lat=ref_lat,
        ref_lon=ref_lon,
    )
    skew = run_layout(
        ring,
        module_h=2.094,
        module_w=1.038,
        n_portrait=1,
        pitch=6.35,
        setback=5.0,
        azimuth=135.0,
        mounting_type="sat",
        modules_per_string=28,
        inter_string_gap_m=0.5,
        ref_lat=ref_lat,
        ref_lon=ref_lon,
    )
    assert ns and skew
    assert ns["total_modules"] != skew["total_modules"]
