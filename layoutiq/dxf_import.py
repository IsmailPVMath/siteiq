"""Import layout geometry from DXF (strings or pre-tagged tracker unit layers)."""

from __future__ import annotations

import io
import re
from collections import Counter
from typing import Any

from shapely.geometry import Polygon, box
from shapely.ops import unary_union

from layoutiq.tracker_styles import DEFAULT_TRACKER_OPTIONS, style_for_unit

try:
    import ezdxf

    HAS_EZDXF = True
except ImportError:
    HAS_EZDXF = False

_UNIT_LAYER_RE = re.compile(r"^(?:PV|TRACKER)[_-]?(\d)S?$", re.I)
_STRING_LAYERS = frozenset(
    {"PV_MODULE", "PV_STRING", "PV_ROWS", "MODULES", "STRINGS", "TABLES"}
)


def _poly_from_entity(entity) -> Polygon | None:
    try:
        if entity.dxftype() == "LWPOLYLINE":
            pts = [(float(p[0]), float(p[1])) for p in entity.get_points()]
        elif entity.dxftype() == "POLYLINE":
            pts = [(float(v.dxf.location.x), float(v.dxf.location.y)) for v in entity.vertices]
        else:
            return None
        if len(pts) < 3:
            return None
        if pts[0] != pts[-1]:
            pts.append(pts[0])
        poly = Polygon(pts)
        if not poly.is_valid:
            poly = poly.buffer(0)
        return poly if not poly.is_empty and poly.area > 1e-6 else None
    except Exception:
        return None


def _layer_unit_size(layer: str) -> int | None:
    if not layer:
        return None
    name = layer.strip().upper().replace(" ", "_")
    m = _UNIT_LAYER_RE.match(name)
    if m:
        return int(m.group(1))
    if name in ("PV_8S", "TRACKER_8S"):
        return 8
    for n in DEFAULT_TRACKER_OPTIONS:
        if name in (f"PV_{n}S", f"TRACKER_{n}S"):
            return n
    return None


def _cluster_strings_into_rows(string_polys: list[Polygon], row_tol: float) -> list[list[Polygon]]:
    if not string_polys:
        return []
    items = sorted(
        enumerate(string_polys),
        key=lambda t: (-t[1].centroid.y, t[1].centroid.x),
    )
    rows: list[list[Polygon]] = []
    row_centroids: list[float] = []
    for _idx, poly in items:
        cy = poly.centroid.y
        placed = False
        for r_i, rcy in enumerate(row_centroids):
            if abs(cy - rcy) <= row_tol:
                rows[r_i].append(poly)
                row_centroids[r_i] = sum(p.centroid.y for p in rows[r_i]) / len(rows[r_i])
                placed = True
                break
        if not placed:
            rows.append([poly])
            row_centroids.append(cy)
    for row in rows:
        row.sort(key=lambda p: p.centroid.x)
    return rows


def _pack_row_units(
    n_strings: int,
    options: list[int] | None = None,
) -> list[int]:
    opts = sorted({int(v) for v in (options or DEFAULT_TRACKER_OPTIONS) if int(v) > 0}, reverse=True)
    remaining = n_strings
    units: list[int] = []
    while remaining > 0:
        chosen = None
        for opt in opts:
            if opt <= remaining:
                chosen = opt
                break
        if chosen is None:
            break
        units.append(chosen)
        remaining -= chosen
    return units


def _read_dxf_doc(data: bytes):
    """Read ASCII or binary DXF bytes."""
    try:
        return ezdxf.read(io.BytesIO(data))
    except Exception:
        return ezdxf.read(io.StringIO(data.decode("utf-8", errors="ignore")))


def parse_layout_dxf(
    data: bytes,
    *,
    modules_per_string: int = 28,
    tracker_string_options: list[int] | None = None,
) -> dict[str, Any]:
    """
    Parse a metric DXF layout file.

    Supports:
    - Pre-tagged tracker unit rectangles on layers PV_8S … PV_1S (or TRACKER_8S …)
    - Generic string/table rectangles on PV_MODULE / PV_ROWS / untagged layers
    """
    if not HAS_EZDXF:
        raise RuntimeError("ezdxf is not installed")

    doc = _read_dxf_doc(data)
    msp = doc.modelspace()

    unit_entries: list[dict[str, Any]] = []
    string_polys: list[Polygon] = []
    boundary_polys: list[Polygon] = []

    for entity in msp:
        layer = (entity.dxf.layer or "").strip().upper()
        poly = _poly_from_entity(entity)
        if poly is None:
            continue

        unit_n = _layer_unit_size(layer)
        if unit_n:
            unit_entries.append({"poly": poly, "unit_strings": unit_n, "source": "layer"})
            continue

        if layer in ("SITE_BOUNDARY", "BOUNDARY", "SETBACK_INSET", "PARCEL"):
            boundary_polys.append(poly)
            continue

        if layer in _STRING_LAYERS or layer.startswith("PV"):
            string_polys.append(poly)
        else:
            # Heuristic: small closed shapes → strings; very large → boundary.
            if poly.area > 50_000:
                boundary_polys.append(poly)
            elif poly.area >= 8:
                string_polys.append(poly)

    if unit_entries and not string_polys:
        return _layout_from_unit_entries(unit_entries, boundary_polys, modules_per_string)

    if not string_polys:
        raise ValueError(
            "No PV string or tracker-unit polygons found in DXF. "
            "Use closed LWPOLYLINEs on PV_MODULE / PV_8S … PV_1S layers."
        )

    return _layout_from_strings(
        string_polys,
        boundary_polys,
        modules_per_string=modules_per_string,
        tracker_string_options=tracker_string_options,
    )


def _layout_from_unit_entries(
    unit_entries: list[dict[str, Any]],
    boundary_polys: list[Polygon],
    modules_per_string: int,
) -> dict[str, Any]:
    tracker_unit_polys = []
    rows_data = []
    total_strings = 0
    for i, entry in enumerate(unit_entries):
        n = int(entry["unit_strings"])
        style = style_for_unit(n)
        tracker_unit_polys.append(
            {
                "poly": entry["poly"],
                "unit_strings": n,
                "row_index": i + 1,
                "unit_index": i + 1,
                "style": style,
            }
        )
        rows_data.append(
            {
                "n_modules": n * modules_per_string,
                "n_strings": n,
                "partial_modules": 0,
                "tracker_units": [n],
                "length_m": round(entry["poly"].bounds[2] - entry["poly"].bounds[0], 2),
            }
        )
        total_strings += n

    all_geom = unary_union([e["poly"] for e in unit_entries])
    site = _largest_boundary(boundary_polys, all_geom)
    return _assemble_layout(
        site=site,
        inset=site,
        string_polys=[],
        rows_polys=[e["poly"] for e in unit_entries],
        rows_data=rows_data,
        tracker_unit_polys=tracker_unit_polys,
        modules_per_string=modules_per_string,
        total_strings=total_strings,
        is_tracker=True,
    )


def _layout_from_strings(
    string_polys: list[Polygon],
    boundary_polys: list[Polygon],
    *,
    modules_per_string: int,
    tracker_string_options: list[int] | None,
) -> dict[str, Any]:
    heights = [p.bounds[3] - p.bounds[1] for p in string_polys]
    median_h = sorted(heights)[len(heights) // 2] if heights else 2.0
    row_tol = max(median_h * 0.6, 1.0)

    rows = _cluster_strings_into_rows(string_polys, row_tol)
    rows_data: list[dict[str, Any]] = []
    rows_polys: list[Polygon] = []
    ordered_strings: list[Polygon] = []
    string_row_local_idx: list[int] = []
    tracker_unit_polys: list[dict[str, Any]] = []
    unit_global = 0

    for r_idx, row_strings in enumerate(rows):
        if not row_strings:
            continue
        units = _pack_row_units(len(row_strings), tracker_string_options)
        row_union = unary_union(row_strings)
        rows_polys.append(row_union)
        rows_data.append(
            {
                "n_modules": len(row_strings) * modules_per_string,
                "n_strings": len(row_strings),
                "partial_modules": 0,
                "tracker_units": units,
                "length_m": round(row_union.bounds[2] - row_union.bounds[0], 2),
            }
        )
        cursor = 0
        for n in units:
            chunk = row_strings[cursor : cursor + n]
            cursor += n
            if len(chunk) < n:
                continue
            merged = unary_union(chunk)
            minx, miny, maxx, maxy = merged.bounds
            unit_poly = box(minx, miny, maxx, maxy)
            tracker_unit_polys.append(
                {
                    "poly": unit_poly,
                    "unit_strings": n,
                    "row_index": r_idx + 1,
                    "unit_index": unit_global + 1,
                    "style": style_for_unit(n),
                }
            )
            unit_global += 1
        for sp in row_strings:
            ordered_strings.append(sp)
            string_row_local_idx.append(r_idx)

    all_strings = unary_union(string_polys)
    site = _largest_boundary(boundary_polys, all_strings)
    inset = site

    total_strings = len(ordered_strings)
    return _assemble_layout(
        site=site,
        inset=inset,
        string_polys=ordered_strings,
        rows_polys=rows_polys,
        rows_data=rows_data,
        tracker_unit_polys=tracker_unit_polys,
        string_row_local_idx=string_row_local_idx,
        modules_per_string=modules_per_string,
        total_strings=total_strings,
        is_tracker=True,
    )


def _largest_boundary(boundary_polys: list[Polygon], fallback_geom) -> Polygon:
    if boundary_polys:
        return max(boundary_polys, key=lambda p: p.area)
    if fallback_geom.geom_type == "Polygon":
        return fallback_geom.convex_hull
    return fallback_geom.convex_hull


def _assemble_layout(
    *,
    site: Polygon,
    inset: Polygon,
    string_polys: list[Polygon],
    rows_polys: list[Polygon],
    rows_data: list[dict[str, Any]],
    tracker_unit_polys: list[dict[str, Any]],
    modules_per_string: int,
    total_strings: int,
    is_tracker: bool,
    string_row_local_idx: list[int] | None = None,
) -> dict[str, Any]:
    total_modules = sum(r["n_modules"] for r in rows_data)
    area_m2 = site.area
    unit_counts: Counter[int] = Counter()
    for u in tracker_unit_polys:
        unit_counts[int(u["unit_strings"])] += 1

    return {
        "poly_m": site,
        "poly_inset": inset,
        "rows_polys": rows_polys,
        "rows_data": rows_data,
        "string_polys": string_polys,
        "string_row_local_idx": string_row_local_idx or [],
        "tracker_unit_polys": tracker_unit_polys,
        "tracker_unit_counts": dict(unit_counts),
        "total_modules": total_modules,
        "total_strings": total_strings,
        "total_tracker_units": len(tracker_unit_polys),
        "total_rows": len(rows_data),
        "area_m2": area_m2,
        "area_ha": round(area_m2 / 10_000, 3),
        "is_tracker": is_tracker,
        "mounting_type": "sat" if is_tracker else "fixed_tilt",
        "modules_per_string": modules_per_string,
        "imported_from_dxf": True,
    }
