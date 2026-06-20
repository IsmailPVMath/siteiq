"""TopoIQ CAD/GIS export helpers — global UTM georef + local centroid packages."""

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


def sanitize_topo_basename(project_name: str, fallback: str = "Project") -> str:
    slug = (project_name or fallback).strip()
    slug = re.sub(r"[^\w\s\-]", "", slug, flags=re.UNICODE)
    slug = re.sub(r"[\s\-]+", "_", slug).strip("_")
    slug = slug[:60] or fallback
    return f"TopoIQ_{slug}"


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
) -> bytes:
    payload = {
        "format": "TopoIQ_reference_v1",
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
        },
        "exports": {
            "local_package": "DXF *_local.dxf and XYZ *_local.csv — Easting/Northing meters from centroid",
            "georef_package": "LandXML *.xml, DXF *_georef.dxf, XYZ *_georef.csv — WGS84 UTM meters",
            "geo_csv": "Lon/Lat/Elevation for GIS and PVsyst — not the primary Civil 3D surface path",
        },
        "analysis": {
            "grid_spacing_m": grid_m,
            "boundary_mode": analysis_mode,
            "enabled_parcels": parcel_count,
        },
        "notes": [
            "Import LandXML or georef DXF for map-aligned workflows in Civil 3D / BricsCAD.",
            "Use local DXF/XYZ to work near drawing origin (0,0) at the centroid.",
            "Multiple disconnected parcels may show TIN seams between separate blocks.",
        ],
    }
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


def export_xyz_local(X: np.ndarray, Y: np.ndarray, Z: np.ndarray, lat_c: float, lon_c: float) -> bytes:
    easting, northing = local_en_from_latlon(X, Y, lon_c, lat_c)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Easting_m", "Northing_m", "Elevation_m"])
    for r in range(X.shape[0]):
        for c in range(X.shape[1]):
            if not np.isnan(Z[r, c]):
                writer.writerow([f"{easting[r, c]:.3f}", f"{northing[r, c]:.3f}", f"{Z[r, c]:.3f}"])
    return buf.getvalue().encode()


def export_xyz_georef(X: np.ndarray, Y: np.ndarray, Z: np.ndarray, lat_c: float, lon_c: float) -> bytes:
    eastings, northings, _ = utm_grids_from_latlon(X, Y, lat_c, lon_c)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["UTM_Easting_m", "UTM_Northing_m", "Elevation_m"])
    for r in range(X.shape[0]):
        for c in range(X.shape[1]):
            if not np.isnan(Z[r, c]):
                writer.writerow([f"{eastings[r, c]:.3f}", f"{northings[r, c]:.3f}", f"{Z[r, c]:.3f}"])
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


def export_landxml_utm(
    X: np.ndarray,
    Y: np.ndarray,
    Z: np.ndarray,
    *,
    site_name: str,
    lat_c: float,
    lon_c: float,
) -> bytes | None:
    pt_idx, faces = _tin_faces_from_grid(Z)
    if len(pt_idx) < 3 or not faces:
        return None

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
    units = ET.SubElement(root, "Units")
    ET.SubElement(units, "Metric", {
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
        "desc": "TopoIQ satellite DEM — merged TIN, WGS84 UTM",
    })
    defn = ET.SubElement(surface, "Definition", {"surfType": "TIN"})
    pnts = ET.SubElement(defn, "Pnts")
    faces_el = ET.SubElement(defn, "Faces")

    for (r, c), i in pt_idx.items():
        n_val = northings[r, c]
        e_val = eastings[r, c]
        z_val = Z[r, c]
        ET.SubElement(pnts, "P", {"id": str(i)}).text = f"{n_val:.3f} {e_val:.3f} {z_val:.3f}"

    for a, b, c in faces:
        ET.SubElement(faces_el, "F").text = f"{a} {b} {c}"

    xml_str = minidom.parseString(ET.tostring(root)).toprettyxml(indent="  ")
    return xml_str.encode("utf-8")


def _add_boundary_polylines(msp, polygon_list, easting_fn, northing_fn, *, closed: bool = True) -> None:
    for coords in polygon_list:
        if not coords or len(coords) < 3:
            continue
        pts = []
        for lon, lat in coords:
            e = easting_fn(lon, lat)
            n = northing_fn(lon, lat)
            pts.append((float(e), float(n)))
        if closed and pts[0] != pts[-1]:
            pts.append(pts[0])
        if len(pts) >= 2:
            msp.add_lwpolyline(pts, dxfattribs={"layer": "BOUNDARY"})


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
) -> bytes | None:
    if not HAS_EZDXF or not HAS_SCIPY:
        return None

    z_valid = Z[~np.isnan(Z)]
    if len(z_valid) == 0:
        return None

    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    doc.layers.add("CONTOUR_MINOR", color=3)
    doc.layers.add("CONTOUR_MAJOR", color=1)
    doc.layers.add("BOUNDARY", color=3 if georef else 5)

    z_min = math.floor(z_valid.min() / minor_int) * minor_int
    z_max = math.ceil(z_valid.max() / minor_int) * minor_int
    levels = np.arange(z_min, z_max + minor_int, minor_int)

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots()
    cs = ax.contour(easting, northing, Z, levels=levels)
    plt.close(fig)

    for i, level in enumerate(cs.levels):
        is_major = abs(level % major_int) < 1e-6
        layer = "CONTOUR_MAJOR" if is_major else "CONTOUR_MINOR"
        for seg in cs.allsegs[i]:
            if len(seg) >= 2:
                pts = [(float(p[0]), float(p[1])) for p in seg]
                msp.add_lwpolyline(pts, dxfattribs={"layer": layer, "elevation": float(level)})

    if polygon_list:
        if georef:
            def _e(lon, lat):
                return latlon_to_utm(lat, lon)[0]

            def _n(lon, lat):
                return latlon_to_utm(lat, lon)[1]
        else:
            m_per_deg_lat = 111_320.0
            m_per_deg_lon = 111_320.0 * math.cos(math.radians(lat_c))

            def _e(lon, lat):
                return (lon - lon_c) * m_per_deg_lon

            def _n(lon, lat):
                return (lat - lat_c) * m_per_deg_lat

        _add_boundary_polylines(msp, polygon_list, _e, _n)

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
