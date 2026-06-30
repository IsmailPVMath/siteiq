"""TerrainIQ CAD/GIS export helpers — global UTM georef + local centroid packages."""

from __future__ import annotations

import csv
import io
import json
import math
import re
import zipfile
from datetime import datetime, timezone
from typing import Any
from xml.dom import minidom
import xml.etree.ElementTree as ET

import numpy as np

try:
    import ezdxf
    HAS_EZDXF = True
except ImportError:
    HAS_EZDXF = False

try:
    import scipy  # noqa: F401 — contour export via matplotlib
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False

_WGS84_A = 6378137.0
_WGS84_F = 1 / 298.257223563
_WGS84_K0 = 0.9996
_M_PER_US_SURVEY_FT = 0.304800609601219


def is_us_project(country: str) -> bool:
    c = (country or "").strip().lower().replace(".", "")
    return c in (
        "us", "usa", "united states", "united states of america",
    )


def export_linear_units(country: str) -> str:
    return "imperial_us_survey" if is_us_project(country) else "metric"


def _linear_scale(units: str) -> float:
    if units == "imperial_us_survey":
        return 1.0 / _M_PER_US_SURVEY_FT
    return 1.0


def _dxf_insunits(units: str) -> int:
    return 2 if units == "imperial_us_survey" else 6


def sanitize_topo_basename(project_name: str, fallback: str = "Project") -> str:
    slug = (project_name or fallback).strip()
    slug = re.sub(r"[^\w\s\-]", "", slug, flags=re.UNICODE)
    slug = re.sub(r"[\s\-]+", "_", slug).strip("_")
    slug = slug[:60] or fallback
    return f"TerrainIQ_{slug}"


def utm_zone(lon: float) -> int:
    return int((lon + 180.0) // 6) + 1


def epsg_utm_wgs84(lat: float, lon: float) -> int:
    zone = utm_zone(lon)
    return (32600 if lat >= 0 else 32700) + zone


def latlon_to_utm(lat: float, lon: float) -> tuple[float, float, int]:
    """WGS84 geographic → UTM easting/northing (meters)."""
    zone = utm_zone(lon)
    lon0 = (zone - 1) * 6 - 180 + 3
    lat_r = math.radians(lat)
    lon_r = math.radians(lon)
    lon0_r = math.radians(lon0)
    e2 = 2 * _WGS84_F - _WGS84_F * _WGS84_F
    e = math.sqrt(e2)
    ep2 = e2 / (1 - e2)
    sin_lat = math.sin(lat_r)
    cos_lat = math.cos(lat_r)
    n = _WGS84_A / math.sqrt(1 - e2 * sin_lat * sin_lat)
    t = math.tan(lat_r) ** 2
    c = ep2 * cos_lat * cos_lat
    a = (lon_r - lon0_r) * cos_lat
    m = _WGS84_A * (
        (1 - e2 / 4 - 3 * e2 ** 2 / 64 - 5 * e2 ** 3 / 256) * lat_r
        - (3 * e2 / 8 + 3 * e2 ** 2 / 32 + 45 * e2 ** 3 / 1024) * math.sin(2 * lat_r)
        + (15 * e2 ** 2 / 256 + 45 * e2 ** 3 / 1024) * math.sin(4 * lat_r)
        - (35 * e2 ** 3 / 3072) * math.sin(6 * lat_r)
    )
    easting = _WGS84_K0 * n * (
        a + (1 - t + c) * a ** 3 / 6
        + (5 - 18 * t + t ** 2 + 72 * c - 58 * ep2) * a ** 5 / 120
    ) + 500_000.0
    northing = _WGS84_K0 * (
        m + n * math.tan(lat_r) * (
            a ** 2 / 2
            + (5 - t + 9 * c + 4 * c ** 2) * a ** 4 / 24
            + (61 - 58 * t + t ** 2 + 600 * c - 330 * ep2) * a ** 6 / 720
        )
    )
    if lat < 0:
        northing += 10_000_000.0
    return easting, northing, zone


def local_en_from_latlon(lon: np.ndarray, lat: np.ndarray, lon_c: float, lat_c: float) -> tuple[np.ndarray, np.ndarray]:
    m_per_deg_lat = 111_320.0
    m_per_deg_lon = 111_320.0 * math.cos(math.radians(lat_c))
    easting = (lon - lon_c) * m_per_deg_lon
    northing = (lat - lat_c) * m_per_deg_lat
    return easting, northing


def utm_grids_from_latlon(X: np.ndarray, Y: np.ndarray, lat_c: float, lon_c: float) -> tuple[np.ndarray, np.ndarray, int]:
    epsg = epsg_utm_wgs84(lat_c, lon_c)
    zone = epsg % 100
    eastings = np.full_like(X, np.nan, dtype=float)
    northings = np.full_like(Y, np.nan, dtype=float)
    for r in range(X.shape[0]):
        for c in range(X.shape[1]):
            if not np.isnan(X[r, c]) and not np.isnan(Y[r, c]):
                e, n, _ = latlon_to_utm(float(Y[r, c]), float(X[r, c]))
                eastings[r, c] = e
                northings[r, c] = n
    return eastings, northings, zone


def build_reference_json(
    *,
    project_name: str,
    lat_c: float,
    lon_c: float,
    elev_c: float,
    grid_m: float,
    epsg: int,
    utm_e: float,
    utm_n: float,
    parcel_count: int,
    analysis_mode: str,
    country: str = "",
    linear_units: str = "metric",
    contour_minor_m: float | None = None,
    contour_major_m: float | None = None,
) -> bytes:
    unit_label = "US survey feet" if linear_units == "imperial_us_survey" else "meters"
    payload = {
        "format": "TerrainIQ_reference_v1",
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "project_name": project_name or "Unnamed",
        "reference_point": {
            "description": "Boundary centroid — local CAD exports use (0,0) at this point",
            "latitude_wgs84": round(lat_c, 8),
            "longitude_wgs84": round(lon_c, 8),
            "elevation_m_amsl": round(elev_c, 3),
        },
        "coordinate_systems": {
            "geographic": "EPSG:4326",
            "projected_utm": f"EPSG:{epsg}",
            "utm_easting_m": round(utm_e, 3),
            "utm_northing_m": round(utm_n, 3),
            "export_linear_units": unit_label,
        },
        "cad_import": {
            "georef_package_units": unit_label,
            "use_georef_for_map_location": True,
            "local_package_note": "Local DXF/XYZ use (0,0) at boundary centroid — not map coordinates.",
            "do_not_scale_on_import": (
                "Coordinates in georef LandXML/DXF already match the declared units. "
                "Do not apply feet↔meter scaling after import."
            ),
        },
        "exports": {
            "local_package": (
                f"DXF *_contours_local.dxf (SITE_BOUNDARY layer) and XYZ *_local.csv — "
                f"from centroid in {unit_label}"
            ),
            "georef_package": (
                f"LandXML *.xml, DXF *_contours_georef.dxf (SITE_BOUNDARY layer), "
                f"XYZ *_georef.csv — WGS84 UTM in {unit_label}"
            ),
            "geo_csv": "Lon/Lat/Elevation for GIS and PVsyst — not the primary CAD surface path",
        },
        "analysis": {
            "grid_spacing_m": grid_m,
            "boundary_mode": analysis_mode,
            "enabled_parcels": parcel_count,
            "project_country": country or "Unknown",
            **(
                {
                    "contour_minor_m": round(float(contour_minor_m), 2),
                    "contour_major_m": round(float(contour_major_m), 2),
                }
                if contour_minor_m is not None and contour_major_m is not None
                else {}
            ),
        },
        "notes": [
            "Import georef LandXML or georef DXF for map-aligned workflows in CAD.",
            "Site parcel linework is on layer SITE_BOUNDARY in contour DXF files and in Parcels/PlanFeatures (LandXML).",
            "Contour lines in DXF are clipped to the site boundary — no rectangular grid edge artifacts.",
            "Use local DXF/XYZ to work near drawing origin (0,0) at the centroid.",
            "Multiple disconnected parcels may show TIN seams between separate blocks.",
        ],
    }
    if is_us_project(country):
        payload["cad_import"]["usa_note"] = (
            "USA project: georef exports use US Survey Feet on WGS84 UTM (EPSG). "
            "Create/open an imperial CAD drawing before import — do not manually scale."
        )
    return json.dumps(payload, indent=2).encode("utf-8")


def export_xyz_geo(X: np.ndarray, Y: np.ndarray, Z: np.ndarray) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Longitude", "Latitude", "Elevation_m"])
    for r in range(X.shape[0]):
        for c in range(X.shape[1]):
            if not np.isnan(Z[r, c]):
                writer.writerow([f"{X[r, c]:.8f}", f"{Y[r, c]:.8f}", f"{Z[r, c]:.3f}"])
    return buf.getvalue().encode()


def export_xyz_local(
    X: np.ndarray, Y: np.ndarray, Z: np.ndarray,
    lat_c: float, lon_c: float, *, units: str = "metric",
) -> bytes:
    easting, northing = local_en_from_latlon(X, Y, lon_c, lat_c)
    scale = _linear_scale(units)
    suffix = "ft" if units == "imperial_us_survey" else "m"
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([f"Easting_{suffix}", f"Northing_{suffix}", f"Elevation_{suffix}"])
    for r in range(X.shape[0]):
        for c in range(X.shape[1]):
            if not np.isnan(Z[r, c]):
                writer.writerow([
                    f"{easting[r, c] * scale:.3f}",
                    f"{northing[r, c] * scale:.3f}",
                    f"{Z[r, c] * scale:.3f}",
                ])
    return buf.getvalue().encode()


def export_xyz_georef(
    X: np.ndarray, Y: np.ndarray, Z: np.ndarray,
    lat_c: float, lon_c: float, *, units: str = "metric",
) -> bytes:
    eastings, northings, _ = utm_grids_from_latlon(X, Y, lat_c, lon_c)
    scale = _linear_scale(units)
    suffix = "ft" if units == "imperial_us_survey" else "m"
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([f"UTM_Easting_{suffix}", f"UTM_Northing_{suffix}", f"Elevation_{suffix}"])
    for r in range(X.shape[0]):
        for c in range(X.shape[1]):
            if not np.isnan(Z[r, c]):
                writer.writerow([
                    f"{eastings[r, c] * scale:.3f}",
                    f"{northings[r, c] * scale:.3f}",
                    f"{Z[r, c] * scale:.3f}",
                ])
    return buf.getvalue().encode()


def _tin_faces_from_grid(Z: np.ndarray) -> tuple[dict[tuple[int, int], int], list[tuple[int, int, int]]]:
    rows, cols = Z.shape
    pt_idx: dict[tuple[int, int], int] = {}
    idx = 1
    for r in range(rows):
        for c in range(cols):
            if not np.isnan(Z[r, c]):
                pt_idx[(r, c)] = idx
                idx += 1
    faces: list[tuple[int, int, int]] = []
    for r in range(rows - 1):
        for c in range(cols - 1):
            if all((r + dr, c + dc) in pt_idx for dr, dc in [(0, 0), (0, 1), (1, 0), (1, 1)]):
                a = pt_idx[(r, c)]
                b = pt_idx[(r, c + 1)]
                cc = pt_idx[(r + 1, c)]
                d = pt_idx[(r + 1, c + 1)]
                faces.append((a, b, cc))
                faces.append((b, d, cc))
    return pt_idx, faces


def _sample_z_nearest(X: np.ndarray, Y: np.ndarray, Z: np.ndarray, lon: float, lat: float) -> float:
    """Nearest valid DEM elevation at a lon/lat vertex."""
    valid = ~np.isnan(Z)
    if not valid.any():
        return 0.0
    d2 = (X - lon) ** 2 + (Y - lat) ** 2
    d2[~valid] = np.inf
    r, c = np.unravel_index(int(np.argmin(d2)), Z.shape)
    return float(Z[r, c])


def _boundary_vertices_utm(
    coords: list,
    *,
    lat_c: float,
    lon_c: float,
    X: np.ndarray,
    Y: np.ndarray,
    Z: np.ndarray,
    linear_scale: float = 1.0,
    closed: bool = True,
) -> list[tuple[float, float, float]]:
    """Convert a lon/lat ring to UTM (northing, easting, elev) vertices."""
    if not coords or len(coords) < 3:
        return []
    ring = list(coords)
    if closed and ring[0] != ring[-1]:
        ring.append(ring[0])
    pts: list[tuple[float, float, float]] = []
    for lon, lat in ring:
        e, n, _ = latlon_to_utm(lat, lon)
        z = _sample_z_nearest(X, Y, Z, lon, lat)
        pts.append((n * linear_scale, e * linear_scale, z * linear_scale))
    return pts


def _pntlist3d_text(pts: list[tuple[float, float, float]]) -> str:
    return " ".join(f"{p[0]:.3f} {p[1]:.3f} {p[2]:.3f}" for p in pts)


def _append_landxml_site_boundaries(
    root: ET.Element,
    polygon_list: list,
    *,
    lat_c: float,
    lon_c: float,
    X: np.ndarray,
    Y: np.ndarray,
    Z: np.ndarray,
    linear_scale: float = 1.0,
) -> None:
    """Parcels + PlanFeatures so CAD tools import parcel linework."""
    valid_polys = [p for p in polygon_list if p and len(p) >= 3]
    if not valid_polys:
        return

    parcels = ET.SubElement(root, "Parcels")
    plan_features = ET.SubElement(root, "PlanFeatures")

    for i, coords in enumerate(valid_polys, start=1):
        pts = _boundary_vertices_utm(
            coords, lat_c=lat_c, lon_c=lon_c, X=X, Y=Y, Z=Z, linear_scale=linear_scale,
        )
        if len(pts) < 2:
            continue
        label = f"Site_Boundary_{i}" if len(valid_polys) > 1 else "Site_Boundary"

        parcel = ET.SubElement(parcels, "Parcel", {
            "name": label,
            "desc": "TerrainIQ parcel linework — closed polyline",
        })
        parcel_geom = ET.SubElement(parcel, "CoordGeom")
        parcel_line = ET.SubElement(parcel_geom, "IrregularLine")
        ET.SubElement(parcel_line, "PntList3D").text = _pntlist3d_text(pts)

        feature = ET.SubElement(plan_features, "PlanFeature", {
            "name": label,
            "desc": "TerrainIQ parcel linework for layout/CAD",
        })
        feature_geom = ET.SubElement(feature, "CoordGeom")
        feature_line = ET.SubElement(feature_geom, "IrregularLine")
        ET.SubElement(feature_line, "PntList3D").text = _pntlist3d_text(pts)


def export_landxml_utm(
    X: np.ndarray,
    Y: np.ndarray,
    Z: np.ndarray,
    *,
    site_name: str,
    lat_c: float,
    lon_c: float,
    polygon_list: list | None = None,
    units: str = "metric",
) -> bytes | None:
    pt_idx, faces = _tin_faces_from_grid(Z)
    if len(pt_idx) < 3 or not faces:
        return None

    linear_scale = _linear_scale(units)
    epsg = epsg_utm_wgs84(lat_c, lon_c)
    zone = epsg % 100
    hemi = "North" if lat_c >= 0 else "South"
    eastings, northings, _ = utm_grids_from_latlon(X, Y, lat_c, lon_c)

    root = ET.Element("LandXML", {
        "xmlns": "http://www.landxml.org/schema/LandXML-1.2",
        "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
        "xsi:schemaLocation": (
            "http://www.landxml.org/schema/LandXML-1.2 "
            "http://www.landxml.org/schema/LandXML1.2/LandXML1.2.xsd"
        ),
        "version": "1.2",
        "date": datetime.now().strftime("%Y-%m-%d"),
        "time": datetime.now().strftime("%H:%M:%S"),
        "language": "English",
        "readOnly": "false",
    })
    units_el = ET.SubElement(root, "Units")
    if units == "imperial_us_survey":
        ET.SubElement(units_el, "Imperial", {
            "areaUnit": "squareFoot",
            "linearUnit": "foot",
            "volumeUnit": "cubicFoot",
            "temperatureUnit": "fahrenheit",
            "pressureUnit": "inchHG",
        })
    else:
        ET.SubElement(units_el, "Metric", {
            "areaUnit": "squareMeter",
            "linearUnit": "meter",
            "volumeUnit": "cubicMeter",
            "temperatureUnit": "celsius",
            "pressureUnit": "milliBars",
        })
    cs = ET.SubElement(root, "CoordinateSystem", {
        "horizontalDatum": "WGS84",
        "horizontalCoordinateSystemName": f"UTM-WGS84 Zone {zone} {hemi}",
        "fileLocation": "",
        "rotationAngle": "0.000000",
    })
    ET.SubElement(cs, "ProjectedCoordinateSystem", {"name": f"EPSG:{epsg}"})

    ET.SubElement(root, "Project", {"name": site_name})
    surfaces = ET.SubElement(root, "Surfaces")
    surface = ET.SubElement(surfaces, "Surface", {
        "name": site_name,
        "desc": (
            "TerrainIQ satellite DEM — merged TIN, WGS84 UTM"
            + (" (US survey feet)" if units == "imperial_us_survey" else " (meters)")
        ),
    })
    defn = ET.SubElement(surface, "Definition", {"surfType": "TIN"})
    pnts = ET.SubElement(defn, "Pnts")
    faces_el = ET.SubElement(defn, "Faces")

    for (r, c), i in pt_idx.items():
        n_val = northings[r, c] * linear_scale
        e_val = eastings[r, c] * linear_scale
        z_val = Z[r, c] * linear_scale
        ET.SubElement(pnts, "P", {"id": str(i)}).text = f"{n_val:.3f} {e_val:.3f} {z_val:.3f}"

    for a, b, c in faces:
        ET.SubElement(faces_el, "F").text = f"{a} {b} {c}"

    if polygon_list:
        _append_landxml_site_boundaries(
            root, polygon_list, lat_c=lat_c, lon_c=lon_c, X=X, Y=Y, Z=Z,
            linear_scale=linear_scale,
        )

    xml_str = minidom.parseString(ET.tostring(root)).toprettyxml(indent="  ")
    return xml_str.encode("utf-8")


def _add_boundary_polylines(
    msp,
    polygon_list,
    vertex_fn,
    *,
    layer: str = "SITE_BOUNDARY",
) -> None:
    """Add closed 3D site-boundary polylines to modelspace."""
    for i, coords in enumerate(polygon_list, start=1):
        if not coords or len(coords) < 3:
            continue
        ring = list(coords)
        if ring[0] != ring[-1]:
            ring.append(ring[0])
        pts = [vertex_fn(lon, lat) for lon, lat in ring]
        if len(pts) >= 2:
            msp.add_lwpolyline(
                [(p[0], p[1]) for p in pts],
                dxfattribs={"layer": layer, "elevation": pts[0][2]},
            )


def _contour_vertex_fn(
    *,
    georef: bool,
    lat_c: float,
    lon_c: float,
    X: np.ndarray,
    Y: np.ndarray,
    Z: np.ndarray,
    scale: float,
):
    """Map (lon, lat) boundary vertices to export XY (+ Z)."""
    if georef:
        def _vertex(lon, lat):
            e, n, _ = latlon_to_utm(lat, lon)
            z = _sample_z_nearest(X, Y, Z, lon, lat)
            return (float(e * scale), float(n * scale), z * scale)
    else:
        m_per_deg_lat = 111_320.0
        m_per_deg_lon = 111_320.0 * math.cos(math.radians(lat_c))

        def _vertex(lon, lat):
            e = (lon - lon_c) * m_per_deg_lon
            n = (lat - lat_c) * m_per_deg_lat
            z = _sample_z_nearest(X, Y, Z, lon, lat)
            return (float(e * scale), float(n * scale), z * scale)
    return _vertex


def _union_site_clip_polygon(polygon_list: list, vertex_fn) -> Any | None:
    """Site boundary union in export XY — used to clip contour edge artifacts."""
    if not polygon_list:
        return None
    try:
        from shapely.geometry import Polygon
        from shapely.ops import unary_union
    except ImportError:
        return None

    polys = []
    for coords in polygon_list:
        if not coords or len(coords) < 3:
            continue
        ring = list(coords)
        if ring[0] != ring[-1]:
            ring.append(ring[0])
        pts = [vertex_fn(lon, lat)[:2] for lon, lat in ring]
        if len(pts) < 3:
            continue
        poly = Polygon(pts)
        if not poly.is_valid:
            poly = poly.buffer(0)
        if not poly.is_empty and poly.is_valid:
            polys.append(poly)
    if not polys:
        return None
    merged = unary_union(polys)
    return merged if not merged.is_empty else None


def _linestrings_from_geom(geom) -> list[list[tuple[float, float]]]:
    """Extract 2D line paths from a Shapely intersection result."""
    if geom is None or geom.is_empty:
        return []
    try:
        from shapely.geometry import GeometryCollection, LineString, MultiLineString
    except ImportError:
        return []

    if isinstance(geom, LineString):
        if len(geom.coords) >= 2:
            return [[(float(x), float(y)) for x, y in geom.coords]]
        return []
    if isinstance(geom, MultiLineString):
        out: list[list[tuple[float, float]]] = []
        for part in geom.geoms:
            out.extend(_linestrings_from_geom(part))
        return out
    if isinstance(geom, GeometryCollection):
        out = []
        for part in geom.geoms:
            out.extend(_linestrings_from_geom(part))
        return out
    return []


def _clip_contour_segment(seg, clip_geom) -> list[list[tuple[float, float]]]:
    """Clip one matplotlib contour segment to the site polygon."""
    if len(seg) < 2:
        return []
    if clip_geom is None:
        return [[(float(p[0]), float(p[1])) for p in seg]]
    try:
        from shapely.geometry import LineString
    except ImportError:
        return [[(float(p[0]), float(p[1])) for p in seg]]
    line = LineString([(float(p[0]), float(p[1])) for p in seg])
    if line.is_empty:
        return []
    return _linestrings_from_geom(clip_geom.intersection(line))


def export_dxf_contours(
    X: np.ndarray,
    Y: np.ndarray,
    Z: np.ndarray,
    *,
    easting: np.ndarray,
    northing: np.ndarray,
    polygon_list: list,
    lat_c: float,
    lon_c: float,
    minor_int: float = 0.5,
    major_int: float = 1.0,
    georef: bool = False,
    units: str = "metric",
) -> bytes | None:
    if not HAS_EZDXF or not HAS_SCIPY:
        return None

    scale = _linear_scale(units)
    easting = easting * scale
    northing = northing * scale
    z_plot = Z * scale
    minor_int = minor_int * scale
    major_int = major_int * scale
    z_valid = z_plot[~np.isnan(z_plot)]
    if len(z_valid) == 0:
        return None

    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = _dxf_insunits(units)
    msp = doc.modelspace()
    doc.layers.add("CONTOUR_MINOR", color=3)
    doc.layers.add("CONTOUR_MAJOR", color=1)
    doc.layers.add("SITE_BOUNDARY", color=3 if georef else 5)

    z_min = math.floor(z_valid.min() / minor_int) * minor_int
    z_max = math.ceil(z_valid.max() / minor_int) * minor_int
    levels = np.arange(z_min, z_max + minor_int, minor_int)

    vertex_fn = None
    clip_geom = None
    if polygon_list:
        vertex_fn = _contour_vertex_fn(
            georef=georef, lat_c=lat_c, lon_c=lon_c, X=X, Y=Y, Z=Z, scale=scale,
        )
        clip_geom = _union_site_clip_polygon(polygon_list, vertex_fn)

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots()
    cs = ax.contour(easting, northing, z_plot, levels=levels)
    plt.close(fig)

    for i, level in enumerate(cs.levels):
        is_major = abs(level % major_int) < 1e-6
        layer = "CONTOUR_MAJOR" if is_major else "CONTOUR_MINOR"
        for seg in cs.allsegs[i]:
            for pts in _clip_contour_segment(seg, clip_geom):
                if len(pts) >= 2:
                    msp.add_lwpolyline(pts, dxfattribs={"layer": layer, "elevation": float(level)})

    if polygon_list and vertex_fn:
        _add_boundary_polylines(msp, polygon_list, vertex_fn)

    stream = io.StringIO()
    doc.write(stream)
    return stream.getvalue().encode("utf-8")


def build_topo_export_zip(
    basename: str,
    *,
    pdf_bytes: bytes | None = None,
    reference_json: bytes | None = None,
    lxml: bytes | None = None,
    xyz_local: bytes | None = None,
    xyz_georef: bytes | None = None,
    xyz_geo: bytes | None = None,
    dxf_local: bytes | None = None,
    dxf_georef: bytes | None = None,
) -> tuple[bytes | None, list[str]]:
    entries: list[tuple[str, bytes]] = []
    if reference_json:
        entries.append((f"{basename}_reference.json", reference_json))
    if pdf_bytes:
        entries.append((f"{basename}_report.pdf", pdf_bytes))
    if lxml:
        entries.append((f"{basename}.xml", lxml))
    if dxf_local:
        entries.append((f"{basename}_contours_local.dxf", dxf_local))
    if dxf_georef:
        entries.append((f"{basename}_contours_georef.dxf", dxf_georef))
    if xyz_local:
        entries.append((f"{basename}_local.csv", xyz_local))
    if xyz_georef:
        entries.append((f"{basename}_georef.csv", xyz_georef))
    if xyz_geo:
        entries.append((f"{basename}_geo.csv", xyz_geo))
    if not entries:
        return None, []
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in entries:
            zf.writestr(name, data)
    return buf.getvalue(), [name for name, _ in entries]
