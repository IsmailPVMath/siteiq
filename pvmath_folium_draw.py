"""
streamlit-folium Draw plugin — shared contract for Project Setup & TopoIQ.

REGRESSION GUARD (fixed 4× as of 2026-06): Do NOT subscribe to ``all_drawings`` or
``last_clicked`` while the Folium Draw polygon tool is active. Those events fire on
every vertex click → Streamlit reruns → map iframe remounts → drawing breaks (dim/refresh).

Only ``last_active_drawing`` reruns when the user *completes* a shape.

See: https://github.com/randyzwitch/streamlit-folium/issues/244
"""

from __future__ import annotations

from typing import Any, Iterable, Optional, Sequence, Tuple

# ── Returned-object contracts (never widen draw mode without reading this file) ──
FOLIUM_DRAW_RETURNED_OBJECTS: Tuple[str, ...] = ("last_active_drawing",)
FOLIUM_PIN_RETURNED_OBJECTS: Tuple[str, ...] = ("last_clicked",)
FOLIUM_DRAW_FORBIDDEN: frozenset = frozenset({"all_drawings", "last_clicked"})


def validate_draw_returned_objects(objects: Optional[Iterable[str]]) -> None:
    """Raise if draw-mode map would rerun on every vertex (known regression)."""
    if objects is None:
        raise ValueError(
            "Folium Draw maps must pass an explicit returned_objects list — "
            "default (all events) breaks polygon drawing."
        )
    bad = FOLIUM_DRAW_FORBIDDEN.intersection(objects)
    if bad:
        raise ValueError(
            f"Folium Draw returned_objects must not include {sorted(bad)} — "
            "use FOLIUM_DRAW_RETURNED_OBJECTS (last_active_drawing only). "
            "See pvmath_folium_draw.py module docstring."
        )
    if "last_active_drawing" not in objects:
        raise ValueError(
            "Folium Draw maps must include 'last_active_drawing' to capture "
            "completed polygons."
        )


def st_folium_with_draw(
    m,
    *,
    map_key: str,
    center: Sequence[float],
    zoom: int,
    height: int = 420,
) -> dict[str, Any]:
    """Render map with Draw tools — safe returned_objects enforced."""
    from streamlit_folium import st_folium

    returned = list(FOLIUM_DRAW_RETURNED_OBJECTS)
    validate_draw_returned_objects(returned)
    return st_folium(
        m,
        width=None,
        height=height,
        returned_objects=returned,
        key=map_key,
        center=(float(center[0]), float(center[1])),
        zoom=int(zoom),
    )


def st_folium_pin_drop(
    m,
    *,
    map_key: str,
    center: Sequence[float],
    zoom: int,
    height: int = 400,
) -> dict[str, Any]:
    """Quick-mode pin drop — last_clicked only (no Draw plugin)."""
    from streamlit_folium import st_folium

    return st_folium(
        m,
        width=None,
        height=height,
        returned_objects=list(FOLIUM_PIN_RETURNED_OBJECTS),
        key=map_key,
        center=(float(center[0]), float(center[1])),
        zoom=int(zoom),
    )


def drawing_to_polygon_latlon(drawing) -> Optional[list]:
    """Completed Draw polygon as [[lat, lon], ...] (Project Setup / SiteIQ)."""
    if not drawing or not isinstance(drawing, dict):
        return None
    geom = drawing.get("geometry", {})
    if geom.get("type") != "Polygon":
        return None
    ring = geom.get("coordinates", [[]])[0]
    if len(ring) < 4:
        return None
    return [[c[1], c[0]] for c in ring]


def drawing_to_polygon_lonlat(drawing) -> Optional[list]:
    """Completed Draw polygon as [(lon, lat), ...] (TopoIQ)."""
    if not drawing or not isinstance(drawing, dict):
        return None
    geom = drawing.get("geometry", {})
    if geom.get("type") == "Polygon":
        ring = geom.get("coordinates", [[]])[0]
        if len(ring) >= 4:
            return [(c[0], c[1]) for c in ring]
    if geom.get("type") == "LineString":
        pts = [(c[0], c[1]) for c in geom.get("coordinates", [])]
        if len(pts) >= 3:
            if pts[0] != pts[-1]:
                pts.append(pts[0])
            return pts
    return None


def polygon_from_map_result(map_data, *, lonlat: bool = False) -> Optional[list]:
    """Read completed polygon from st_folium result (prefers last_active_drawing)."""
    if not map_data:
        return None
    convert = drawing_to_polygon_lonlat if lonlat else drawing_to_polygon_latlon
    active = map_data.get("last_active_drawing")
    if active:
        poly = convert(active)
        if poly:
            return poly
    # Legacy fallback when reading old cached results — do not use in returned_objects.
    drawings = map_data.get("all_drawings")
    if isinstance(drawings, list):
        for feat in reversed(drawings):
            poly = convert(feat)
            if poly:
                return poly
    return None


def draw_signature(poly: list, *, max_pts: int = 16) -> Optional[tuple]:
    if not poly or len(poly) < 3:
        return None
    pts = poly[:-1] if len(poly) > 1 and poly[0] == poly[-1] else poly
    return tuple(round(p[0], 5) for p in pts[:max_pts])
