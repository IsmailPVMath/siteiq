"""DXF layout import tests."""

import io

import ezdxf

from pvmath_workflow.imported_layout import build_imported_layout_detail


def _dxf_with_strings() -> bytes:
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    doc.layers.add("PV_MODULE")
    x0, y0 = 0.0, 0.0
    w, h = 29.0, 2.1
    gap = 0.5
    for i in range(6):
        x = x0 + i * (w + gap)
        pts = [(x, y0), (x + w, y0), (x + w, y0 + h), (x, y0 + h), (x, y0)]
        msp.add_lwpolyline(pts, close=True, dxfattribs={"layer": "PV_MODULE"})
    buf = io.StringIO()
    doc.write(buf)
    return buf.getvalue().encode("utf-8")


def test_import_dxf_groups_strings_into_tracker_units():
    detail = build_imported_layout_detail(
        _dxf_with_strings(),
        config_key="SAT_1P",
        pitch_m=6.5,
        ref_lat=32.0,
        ref_lon=-96.5,
        modules_per_string=28,
        tracker_string_options=[6, 5, 4, 3],
    )
    assert detail["total_modules"] == 6 * 28
    assert detail["total_tracker_units"] >= 1
    kinds = {f["properties"]["kind"] for f in detail["geojson"]["features"]}
    assert "tracker_unit" in kinds
