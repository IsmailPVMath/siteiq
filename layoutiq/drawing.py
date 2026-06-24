"""Matplotlib layout schematic export."""

from __future__ import annotations

import io
import math

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches


def make_layout_drawing(
    layout: dict, project_name: str, module_wp: int, azimuth: float
) -> bytes:
    fig, ax = plt.subplots(figsize=(13, 10))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("#e8f4e8")

    def _draw_poly(p, fc, ec, alpha, lw, zorder, ls="-"):
        if p.geom_type == "Polygon" and not p.is_empty:
            x, y = p.exterior.xy
            ax.fill(x, y, facecolor=fc, alpha=alpha, zorder=zorder)
            ax.plot(x, y, color=ec, linewidth=lw, linestyle=ls, zorder=zorder + 1)
        elif p.geom_type in ("MultiPolygon", "GeometryCollection"):
            for g in p.geoms:
                if hasattr(g, "exterior"):
                    _draw_poly(g, fc, ec, alpha, lw, zorder, ls)

    _draw_poly(layout["poly_m"], "#aaaaaa", "#666666", 0.18, 1.2, 1)
    _draw_poly(layout["poly_inset"], "#88aa88", "#888888", 0.10, 0.7, 2, "--")

    for rp in layout["rows_polys"]:
        _draw_poly(rp, "#2e7d32", "#1b5e20", 0.88, 0.3, 3)

    ax.set_aspect("equal")
    ax.set_xlabel("East →  (metres from centroid)", fontsize=9, labelpad=6)
    ax.set_ylabel("North ↑  (metres from centroid)", fontsize=9, labelpad=6)
    ax.tick_params(labelsize=8)
    ax.grid(True, alpha=0.25, linewidth=0.5)
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
        arrowprops=dict(arrowstyle="->", color="#1a2e1a", lw=2),
    )
    ax.text(
        na_x,
        na_y + dy * 0.01,
        "N",
        ha="center",
        va="bottom",
        fontsize=11,
        fontweight="bold",
        color="#1a2e1a",
    )

    raw_len = dx * 0.15
    mag = 10 ** math.floor(math.log10(raw_len))
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
        f"{layout['total_rows']} rows  |  "
        f"{dc_kwp:,.0f} kWp  |  {layout['area_ha']} ha  |  "
        f"{mount_str}"
    )
    ax.set_title(
        f"Layout — {project_name}\n{summary}",
        fontsize=10,
        fontweight="bold",
        pad=10,
        color="#1a1a2e",
    )

    ax.legend(
        handles=[
            mpatches.Patch(color="#2e7d32", alpha=0.88, label="PV rows"),
            mpatches.Patch(color="#aaaaaa", alpha=0.18, label="Site boundary"),
            mpatches.Patch(color="#88aa88", alpha=0.10, label="Setback inset", linestyle="--"),
        ],
        fontsize=8.5,
        loc="lower right",
        framealpha=0.85,
    )

    plt.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    return buf.getvalue()
