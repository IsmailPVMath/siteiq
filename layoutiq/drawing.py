"""Matplotlib layout schematic export."""

from __future__ import annotations

import io
import math

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

from layoutiq.tracker_styles import TRACKER_UNIT_STYLES
from layoutiq.tracker_units import build_tracker_unit_polys


def make_layout_drawing(
    layout: dict, project_name: str, module_wp: int, azimuth: float
) -> bytes:
    fig, ax = plt.subplots(figsize=(13, 10))
    fig.patch.set_facecolor("white")
    # Plane / neutral background for A3 top view (centred schematic).
    ax.set_facecolor("#f4f4f5")

    def _draw_poly(p, fc, ec, alpha, lw, zorder, ls="-"):
        if p.geom_type == "Polygon" and not p.is_empty:
            x, y = p.exterior.xy
            ax.fill(x, y, facecolor=fc, alpha=alpha, zorder=zorder)
            ax.plot(x, y, color=ec, linewidth=lw, linestyle=ls, zorder=zorder + 1)
        elif p.geom_type in ("MultiPolygon", "GeometryCollection"):
            for g in p.geoms:
                if hasattr(g, "exterior"):
                    _draw_poly(g, fc, ec, alpha, lw, zorder, ls)

    _draw_poly(layout["poly_m"], "#d4d4d8", "#71717a", 0.35, 1.0, 1)
    _draw_poly(layout["poly_inset"], "#e4e4e7", "#a1a1aa", 0.25, 0.6, 2, "--")

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
    ax.set_xlabel("East →  (metres from reference)", fontsize=9, labelpad=6)
    ax.set_ylabel("North ↑  (metres from reference)", fontsize=9, labelpad=6)
    ax.tick_params(labelsize=8)
    ax.grid(True, alpha=0.2, linewidth=0.4, color="#a1a1aa")
    ax.spines[["top", "right"]].set_visible(False)

    xl, xr = ax.get_xlim()
    yb, yt = ax.get_ylim()
    dx, dy = xr - xl, yt - yb
    na_x = xr - dx * 0.05
    na_y = yt - dy * 0.04
    ax.annotate(
        "",
        xy=(na_x, na_y),
        xytext=(na_x, na_y - dy * 0.08),
        arrowprops=dict(arrowstyle="->", color="#18181b", lw=2),
    )
    ax.text(
        na_x,
        na_y + dy * 0.01,
        "N",
        ha="center",
        va="bottom",
        fontsize=11,
        fontweight="bold",
        color="#18181b",
    )

    raw_len = dx * 0.15
    mag = 10 ** math.floor(math.log10(raw_len)) if raw_len > 0 else 1
    scale_m = round(raw_len / mag) * mag or mag
    sx = xl + dx * 0.04
    sy = yb + dy * 0.03
    ax.plot([sx, sx + scale_m], [sy, sy], "k-", lw=2.5)
    ax.text(
        sx + scale_m / 2,
        sy + dy * 0.012,
        f"{int(scale_m)} m",
        ha="center",
        va="bottom",
        fontsize=8,
    )

    dc_kwp = layout["total_modules"] * module_wp / 1000
    mount_str = (
        "Single-Axis Tracker (SAT)"
        if layout.get("is_tracker")
        else f"Fixed Tilt · Az {azimuth}°"
    )
    summary = (
        f"{layout['total_modules']:,} modules  |  "
        f"{layout.get('total_tracker_units', layout['total_rows'])} tracker units  |  "
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

    ax.legend(
        handles=handles,
        fontsize=8.5,
        loc="lower right",
        framealpha=0.92,
        title="Tracker units",
    )

    plt.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return buf.getvalue()
