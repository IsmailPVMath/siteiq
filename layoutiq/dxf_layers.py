"""PVMath layout DXF layer names and local → UTM coordinate transforms."""

from __future__ import annotations

from typing import Any, Iterable, List, Optional, Sequence, Tuple

from layoutiq.coords import xy_to_latlon

try:
    from pvmath_topo_export import epsg_utm_wgs84, latlon_to_utm
except ImportError:
    epsg_utm_wgs84 = None  # type: ignore
    latlon_to_utm = None  # type: ignore

# Standard PVMath DXF layers (prefix keeps customer CAD templates tidy).
LAYER_SITE = "PVM_SiteBoundary"
LAYER_BUILDABLE = "PVM_Buildable"
LAYER_STRINGS = "PVM_Strings"
LAYER_LABELS = "PVM_Labels"
LAYER_TRACKER_PREFIX = "PVM_Tr_"
LAYER_FIXED_PREFIX = "PVM_F_"

# Legacy names still accepted on import.
LEGACY_SITE = {"SITE_BOUNDARY", "BOUNDARY", "PARCEL", LAYER_SITE}
LEGACY_BUILDABLE = {"SETBACK_INSET", LAYER_BUILDABLE}
LEGACY_STRINGS = {"PV_MODULE", "PV_STRING", "MODULES", "STRINGS", "TABLES", LAYER_STRINGS}
LEGACY_ROWS = {"PV_ROWS", "TRACKERS"}


def tracker_layer(unit_strings: int) -> str:
    return f"{LAYER_TRACKER_PREFIX}{int(unit_strings)}S"


def fixed_layer(n_portrait: int) -> str:
    return f"{LAYER_FIXED_PREFIX}{int(n_portrait)}P"


def _utm_point(x: float, y: float, ref_lat: float, ref_lon: float) -> Tuple[float, float]:
    if latlon_to_utm is None:
        raise RuntimeError("pvmath_topo_export unavailable")
    lat, lon = xy_to_latlon([(x, y)], ref_lat, ref_lon)[0]
    easting, northing, _ = latlon_to_utm(lat, lon)
    return easting, northing


def poly_to_utm_coords(
    poly: Any,
    ref_lat: float,
    ref_lon: float,
) -> Tuple[List[Tuple[float, float]], Optional[int]]:
    """Convert a local-metric shapely polygon to UTM exterior ring + EPSG code."""
    if epsg_utm_wgs84 is None or latlon_to_utm is None:
        raise RuntimeError("pvmath_topo_export unavailable")
    lat0, lon0 = xy_to_latlon([(poly.centroid.x, poly.centroid.y)], ref_lat, ref_lon)[0]
    epsg = epsg_utm_wgs84(lat0, lon0)
    ring = [_utm_point(x, y, ref_lat, ref_lon) for x, y in poly.exterior.coords]
    return ring, epsg


def iter_poly_rings_utm(
    poly: Any,
    ref_lat: float,
    ref_lon: float,
) -> Iterable[Tuple[List[Tuple[float, float]], Optional[int]]]:
    """Yield exterior + interior rings in UTM."""
    if poly.is_empty:
        return
    if poly.geom_type == "Polygon":
        ext, epsg = poly_to_utm_coords(poly, ref_lat, ref_lon)
        yield ext, epsg
        for interior in poly.interiors:
            hole = [_utm_point(x, y, ref_lat, ref_lon) for x, y in interior.coords]
            yield hole, epsg
    elif poly.geom_type in ("MultiPolygon", "GeometryCollection"):
        for geom in poly.geoms:
            yield from iter_poly_rings_utm(geom, ref_lat, ref_lon)
