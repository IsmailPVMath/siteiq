"""Tests for project setup validation."""

from pvmath_project_setup import merge_project_data, normalize_legacy_project_data, validate_project_data


def test_validate_requires_name():
    result = validate_project_data({"center": {"lat": 48.0, "lon": 11.0}})
    assert result["valid"] is False
    assert any(i["field"] == "name" for i in result["issues"])


def test_validate_with_boundary_runs_full_pipeline():
    data = normalize_legacy_project_data(
        {
            "name": "Test",
            "country": "Germany",
            "center": {"lat": 48.0, "lon": 11.0},
            "site_boundary_geojson": {
                "type": "Polygon",
                "coordinates": [[[11, 48], [11.01, 48], [11.01, 48.01], [11, 48.01], [11, 48]]],
            },
            "workflow": {"area_ha": 25},
        }
    )
    result = validate_project_data(data)
    assert result["valid"] is True
    assert result["readiness"]["has_boundary"] is True
    assert "YieldIQ" in result["modules_to_run"]


def test_merge_preserves_existing_keys():
    existing = {"name": "A", "workflow": {"area_ha": 10, "client": "X"}}
    patch = {"workflow": {"area_ha": 20}}
    merged = merge_project_data(existing, patch)
    assert merged["workflow"]["area_ha"] == 20
    assert merged["workflow"]["client"] == "X"
