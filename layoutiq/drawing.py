"""Matplotlib layout schematic export."""

from __future__ import annotations

import io
import math

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.lines as mlines
from layoutiq.tracker_styles import TRACKER_UNIT_STYLES
from layoutiq.tracker_units import build_tracker_unit_polys

try:
    from shapely.geometry import shape as _shapely_shape
    from shapely.ops import transform as _shapely_transform

    _HAS_SHAPELY = True
except Exception:  # pragma: no cover
    _HAS_SHAPELY = False

# GIS constraint colours (match the React map / gis_constraints.LAYER_STYLES).
_LAYER_COLORS = {
    "roads": "#64748b",
    "railways": "#475569",
    "buildings": "#dc2626",
    "rivers": "#2563eb",
    "lakes": "#1d4ed8",
    "canals": "#0284c7",
    "forests": "#15803d",
    "water_bodies": "#0369a1",
    "transmission_lines": "#ea580c",
}
_LAYER_LABELS = {
    "roads": "Roads",
    "railways": "Railways",
    "buildings": "Buildings",
    "rivers": "Rivers / streams",
    "lakes": "Lakes",
    "canals": "Canals",
    "forests": "Forest / wood",
    "water_bodies": "Water bodies",
    "transmission_lines": "Transmission lines",
}
_LINE_CATEGORIES = {"transmission_lines", "rivers", "canals", "roads", "railways"}


def _project_to_metres(geojson, ref_lat: float, ref_lon: float):
    """GeoJSON (lon/lat) geometry/feature/collection → shapely geom(s) in local metres."""
    if not geojson or not _HAS_SHAPELY:
        return []
    cos_ref = math.cos(math.radians(ref_lat))
    R = 6_371_000.0

    def _fwd(lon, lat, z=None):
        x = (lon - ref_lon) * math.pi / 180 * R * cos_ref
        y = (lat - ref_lat) * math.pi / 180 * R
        return (x, y)

    geoms = []

    def _walk(node):
        if not isinstance(node, dict):
            return
        t = node.get("type")
        if t == "FeatureCollection":
            for f in node.get("features") or []:
                _walk(f)
        elif t == "Feature":
            _walk(node.get("geometry"))
        elif t == "GeometryCollection":
            for g in node.get("geometries") or []:
                _walk(g)
        elif t:
            try:
                geom = _shapely_shape(node)
                if geom and not geom.is_empty:
                    geoms.append(_shapely_transform(_fwd, geom))
            except Exception:
                pass

    _walk(geojson)
    return geoms


def make_layout_drawing(
    layout: dict,
    project_name: str,
    module_wp: int,
    azimuth: float,
    *,
    excluded_geojson=None,
    constraint_layers=None,
    big: bool = False,
) -> bytes:
    ref_lat = layout.get("ref_lat")
    ref_lon = layout.get("ref_lon")
    fig, ax = plt.subplots(figsize=(18.5, 13) if big else (13, 10))
    fig.patch.set_facecolor("white")
    # Plane / neutral background for engineering top view (centred schematic).
    ax.set_facecolor("#f4f4f5")

    def _draw_poly(p, fc, ec, alpha, lw, zorder, ls="-", hatch=None):
        if p.geom_type == "Polygon" and not p.is_empty:
            x, y = p.exterior.xy
            ax.fill(x, y, facecolor=fc, alpha=alpha, zorder=zorder, hatch=hatch, edgecolor=ec)
            ax.plot(x, y, color=ec, linewidth=lw, linestyle=ls, zorder=zorder + 1)
            for interior in p.interiors:
                hx, hy = interior.xy
                ax.plot(hx, hy, color=ec, linewidth=lw * 0.6, linestyle=ls, zorder=zorder + 1)
        elif p.geom_type in ("MultiPolygon", "GeometryCollection"):
            for g in p.geoms:
                if hasattr(g, "exterior"):
                    _draw_poly(g, fc, ec, alpha, lw, zorder, ls, hatch)

    def _draw_line(p, color, lw, zorder):
        if p.geom_type == "LineString" and not p.is_empty:
            x, y = p.xy
            ax.plot(x, y, color=color, linewidth=lw, zorder=zorder, solid_capstyle="round")
        elif p.geom_type in ("MultiLineString", "GeometryCollection"):
            for g in p.geoms:
                _draw_line(g, color, lw, zorder)

    _draw_poly(layout["poly_m"], "#d4d4d8", "#71717a", 0.35, 1.0, 1)
    _draw_poly(layout["poly_inset"], "#e4e4e7", "#a1a1aa", 0.25, 0.6, 2, "--")

    # ── GIS constraint layers (rivers, transmission lines, roads, buildings…) ──
    present_categories: list[str] = []
    if constraint_layers and ref_lat is not None:
        for cat, layer in constraint_layers.items():
            color = _LAYER_COLORS.get(cat, "#9ca3af")
            geoms = _project_to_metres(layer, ref_lat, ref_lon)
            drew = False
            for g in geoms:
                if g.geom_type in ("LineString", "MultiLineString"):
                    _draw_line(g, color, 1.6, 6)
                    drew = True
                elif g.geom_type in ("Polygon", "MultiPolygon", "GeometryCollection"):
                    _draw_poly(g, color, color, 0.18, 0.6, 4)
                    drew = True
            if drew:
                present_categories.append(cat)

    # ── Excluded / keep-out union (red hatched — no modules placed here) ───────
    has_excluded = False
    if excluded_geojson and ref_lat is not None:
        for g in _project_to_metres(excluded_geojson, ref_lat, ref_lon):
            _draw_poly(g, "#ef4444", "#dc2626", 0.16, 0.8, 3, ls="--", hatch="////")
            has_excluded = True

    # String outlines (thin) under tracker unit boxes.
    for sp in layout.get("string_polys") or []:
        _draw_poly(sp, "#bfdbfe", "#93c5fd", 0.35, 0.2, 3)

    unit_polys = layout.get("tracker_unit_polys") or build_tracker_unit_polys(layout)
    legend_sizes: set[int] = set()
    for unit in unit_polys:
        style = unit.get("style") or TRACKER_UNIT_STYLES.get(unit["unit_strings"], {})
        n = int(unit["unit_strings"])
        legend_sizes.add(n)
        _draw_poly(
            unit["poly"],
            style.get("fill", "#2563eb"),
            style.get("stroke", "#1e40af"),
            0.55,
            1.2,
            4,
        )

    if not unit_polys:
        for rp in layout.get("rows_polys") or []:
            _draw_poly(rp, "#2e7d32", "#1b5e20", 0.88, 0.3, 3)

    ax.set_aspect("equal")
    ax.set_xlabel("East \u2192  (metres from reference)", fontsize=10, labelpad=6)
    ax.set_ylabel("North \u2191  (metres from reference)", fontsize=10, labelpad=6)
    ax.tick_params(labelsize=8)
    ax.grid(True, alpha=0.2, linewidth=0.4, color="#a1a1aa")
    ax.spines[["top", "right"]].set_visible(False)

    # Lock the view to the SITE extent (boundary + arrays), so distant rivers /
    # transmission lines never zoom the drawing out. Constraints are clipped to
    # this window by the axes.
    bx0 = by0 = float("inf")
    bx1 = by1 = float("-inf")
    for g in [layout.get("poly_m"), layout.get("poly_inset")]:
        if g is not None and not g.is_empty:
            gx0, gy0, gx1, gy1 = g.bounds
            bx0, by0 = min(bx0, gx0), min(by0, gy0)
            bx1, by1 = max(bx1, gx1), max(by1, gy1)
    for coll in (layout.get("tracker_unit_polys") or []):
        poly = coll.get("poly") if isinstance(coll, dict) else coll
        if poly is not None and not poly.is_empty:
            gx0, gy0, gx1, gy1 = poly.bounds
            bx0, by0 = min(bx0, gx0), min(by0, gy0)
            bx1, by1 = max(bx1, gx1), max(by1, gy1)
    if math.isfinite(bx0) and bx1 > bx0 and by1 > by0:
        mx = (bx1 - bx0) * 0.04
        my = (by1 - by0) * 0.04
        ax.set_xlim(bx0 - mx, bx1 + mx)
        ax.set_ylim(by0 - my, by1 + my)

    xl, xr = ax.get_xlim()
    yb, yt = ax.get_ylim()
    dx, dy = xr - xl, yt - yb
    na_lw = 3.0 if big else 2.0
    na_fs = 16 if big else 11
    na_x = xr - dx * 0.05
    na_y = yt - dy * 0.05
    ax.annotate(
        "",
        xy=(na_x, na_y),
        xytext=(na_x, na_y - dy * 0.09),
        arrowprops=dict(arrowstyle="-|>", color="#18181b", lw=na_lw, mutation_scale=22 if big else 16),
    )
    ax.text(
        na_x,
        na_y + dy * 0.012,
        "N",
        ha="center",
        va="bottom",
        fontsize=na_fs,
        fontweight="bold",
        color="#18181b",
    )

    raw_len = dx * 0.15
    mag = 10 ** math.floor(math.log10(raw_len)) if raw_len > 0 else 1
    scale_m = round(raw_len / mag) * mag or mag
    sx = xl + dx * 0.04
    sy = yb + dy * 0.03
    ax.plot([sx, sx + scale_m], [sy, sy], "k-", lw=3.0 if big else 2.5)
    ax.text(
        sx + scale_m / 2,
        sy + dy * 0.012,
        f"{int(scale_m)} m",
        ha="center",
        va="bottom",
        fontsize=9 if big else 8,
        fontweight="bold",
    )

    dc_kwp = layout["total_modules"] * module_wp / 1000
    is_tracker = bool(layout.get("is_tracker"))
    mount_str = (
        "Single-Axis Tracker (SAT)"
        if is_tracker
        else f"Fixed Tilt · Az {azimuth}°"
    )
    if is_tracker:
        unit_total = len(unit_polys) or layout.get("total_tracker_units") or layout["total_rows"]
        unit_label = "tracker units"
    else:
        unit_total = layout["total_rows"]
        unit_label = "rows"
    summary = (
        f"{layout['total_modules']:,} modules  |  "
        f"{unit_total:,} {unit_label}  |  "
        f"{dc_kwp:,.0f} kWp  |  {layout['area_ha']} ha  |  "
        f"{mount_str}"
    )
    ax.set_title(
        f"Layout — {project_name}\n{summary}",
        fontsize=10,
        fontweight="bold",
        pad=10,
        color="#18181b",
    )

    handles = [
        mpatches.Patch(color="#d4d4d8", alpha=0.35, label="Site boundary"),
    ]
    for n in sorted(legend_sizes, reverse=True):
        st = TRACKER_UNIT_STYLES.get(n, {})
        handles.append(
            mpatches.Patch(
                color=st.get("fill", "#64748b"),
                alpha=0.55,
                label=st.get("label", f"{n}S"),
            )
        )
    if not legend_sizes:
        handles.append(mpatches.Patch(color="#2e7d32", alpha=0.88, label="PV rows"))

    if has_excluded:
        handles.append(
            mpatches.Patch(facecolor="#ef4444", edgecolor="#dc2626", alpha=0.4, hatch="////", label="Excluded (no modules)")
        )
    for cat in present_categories:
        color = _LAYER_COLORS.get(cat, "#9ca3af")
        label = _LAYER_LABELS.get(cat, cat.replace("_", " ").title())
        if cat in _LINE_CATEGORIES:
            handles.append(mlines.Line2D([], [], color=color, lw=2.2, label=label))
        else:
            handles.append(mpatches.Patch(color=color, alpha=0.3, label=label))

    if big:
        # A1 sheet: dock the legend in the right margin (outside the plot) so it
        # never overlaps the array. bbox_inches="tight" keeps it on the canvas.
        leg = ax.legend(
            handles=handles,
            fontsize=9,
            loc="upper left",
            bbox_to_anchor=(1.015, 1.0),
            borderaxespad=0.0,
            framealpha=1.0,
            edgecolor="#d4d4d8",
            title="Legend",
            labelspacing=0.7,
            handlelength=1.6,
        )
    else:
        leg = ax.legend(
            handles=handles,
            fontsize=8.5,
            loc="upper right",
            framealpha=0.95,
            edgecolor="#d4d4d8",
            title="Legend",
        )
    leg.get_title().set_fontweight("bold")

    plt.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return buf.getvalue()
