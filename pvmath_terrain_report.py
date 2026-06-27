"""TerrainIQ terrain analytics, map rendering, and PDF report generation."""
from __future__ import annotations

import io
import math
from datetime import datetime, timezone
from typing import Optional

import numpy as np

try:
    from scipy.ndimage import gaussian_filter
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False

from pvmath_capacity import (  # noqa: F401 — re-export for backward compatibility
    GCR_REF,
    GCR_SCREEN_LO,
    GCR_SCREEN_HI,
    _SCREENING_GCR,
    config_mwp_screen,
    config_mwp_screen_2p,
    site_capacity_mwp,
    site_capacity_mw,
    site_capacity_screen,
    site_capacity_screen_2p,
    capacity_range_mw,
    capacity_band,
    format_mwp_range,
    format_density_range,
    capacity_footnote_global,
    capacity_basis_sentence,
)
from pvmath_pdf import append_pdf_footer, format_siteiq_companion_note


# ── Slope thresholds ───────────────────────────────────────────────────────────

FIXED_THRESHOLDS = [
    ("Excellent", "≤ 5%", "Ideal for fixed-tilt ground mount"),
    ("Acceptable", "≤ 10%", "Feasible; some earthworks expected"),
    ("Challenging", "≤ 15%", "Significant earthworks required"),
    ("Critical", "> 15%", "Likely not viable without major grading"),
]

TRACKER_THRESHOLDS = [
    ("Excellent", "≤ 3%", "Ideal for single-axis tracker"),
    ("Acceptable", "≤ 6%", "Feasible; grading may be needed"),
    ("Challenging", "≤ 10%", "Steep for trackers; civil study required"),
    ("Critical", "> 10%", "Too steep for standard tracker layout"),
]


def _verdict_from_mean(mean_pct: float, mount_type: str) -> tuple[str, str]:
    if mount_type == "Single-Axis Tracker":
        if mean_pct <= 3:
            return "Excellent Terrain (Tracker)", (
                f"Mean slope {mean_pct:.1f}% — within tracker excellent threshold (≤3%)."
            )
        if mean_pct <= 6:
            return "Good Terrain (Tracker)", (
                f"Mean slope {mean_pct:.1f}% — acceptable for tracker with possible grading (≤6%)."
            )
        if mean_pct <= 10:
            return "Moderate Terrain (Tracker)", (
                f"Mean slope {mean_pct:.1f}% — challenging for trackers; detailed civil study required."
            )
        return "Challenging Terrain (Tracker)", (
            f"Mean slope {mean_pct:.1f}% — exceeds typical tracker limits; major grading likely."
        )
    if mean_pct <= 5:
        return "Excellent Terrain (Fixed Tilt)", (
            f"Mean slope {mean_pct:.1f}% — within fixed-tilt excellent threshold (≤5%)."
        )
    if mean_pct <= 10:
        return "Good Terrain (Fixed Tilt)", (
            f"Mean slope {mean_pct:.1f}% — acceptable for fixed tilt (≤10%)."
        )
    if mean_pct <= 15:
        return "Moderate Terrain (Fixed Tilt)", (
            f"Mean slope {mean_pct:.1f}% — challenging; significant earthworks expected."
        )
    return "Challenging Terrain (Fixed Tilt)", (
        f"Mean slope {mean_pct:.1f}% — likely requires major grading or layout revision."
    )


def verdict_for_mount(
    mean_pct: float,
    mount_type: str,
    extras: dict | None = None,
) -> tuple[str, str]:
    """Engineering verdict — tracker wording softens when cross-row grades flag review zones."""
    label, detail = _verdict_from_mean(mean_pct, mount_type)
    if mount_type != "Single-Axis Tracker" or not extras:
        return label, detail

    cross_p95 = extras.get("cross_row_p95")
    pct_over_6 = extras.get("pct_cross_over_6")
    if cross_p95 is None:
        return label, detail

    needs_review = cross_p95 > 5.0 or (pct_over_6 is not None and pct_over_6 > 2.0)
    if not needs_review:
        return label, detail

    if "Excellent" in label:
        zone_note = (
            f"{pct_over_6:.1f}% of area >6% cross-row" if pct_over_6 is not None else "elevated cross-row grades"
        )
        return (
            "Mostly Excellent (Tracker) — Review Zones",
            (
                f"Mean slope {mean_pct:.1f}% — mostly excellent tracker terrain, but cross-row "
                f"95th percentile is {cross_p95:.1f}% and {zone_note} — localized grading/clearance "
                "review recommended before pile layout."
            ),
        )

    detail += (
        f" Cross-row 95th %ile {cross_p95:.1f}%"
        + (f"; {pct_over_6:.1f}% of area >6% cross-row" if pct_over_6 is not None else "")
        + " — review clearance in steeper zones."
    )
    return label, detail


def calculate_terrain_score(
    mean_slope: float,
    max_slope: float,
    extras: dict | None = None,
) -> int:
    """Deterministic 0–100 terrain score from mean slope, peaks, and cross-row grades."""
    m = float(mean_slope)
    if m <= 2.5:
        base = 94
    elif m <= 3:
        base = 92
    elif m <= 5:
        base = 88
    elif m <= 6:
        base = 80
    elif m <= 10:
        base = 66
    elif m <= 15:
        base = 52
    else:
        base = 38

    if max_slope > 10:
        base -= 3
    if max_slope > 15:
        base -= 5

    ex = extras or {}
    cr_p95 = ex.get("cross_row_p95")
    pct_over_6 = ex.get("pct_cross_over_6")
    if cr_p95 is not None and cr_p95 > 5:
        base -= 4
    if pct_over_6 is not None and pct_over_6 > 2:
        base -= 3

    return max(0, min(100, round(base)))


def get_terrain_score_label(score: int, verdict_tracker_label: str) -> str:
    """Short label for Terrain Score line — aligns with engineering verdict wording."""
    if "Mostly Excellent" in verdict_tracker_label:
        return "Mostly Excellent"
    if score >= 90:
        return "Excellent"
    if score >= 80:
        return "Very Good"
    if score >= 70:
        return "Good"
    if score >= 60:
        return "Acceptable"
    if score >= 45:
        return "Challenging"
    return "Critical"


def _driver_impact_for_mean(mean_pct: float) -> tuple[str, str]:
    if mean_pct <= 2.5:
        return "Strong positive", "positive"
    if mean_pct <= 5:
        return "Strong positive", "positive"
    if mean_pct <= 6:
        return "Acceptable", "neutral"
    if mean_pct <= 10:
        return "Moderate constraint", "warn"
    return "Significant constraint", "warn"


def build_terrain_drivers(
    mean_slope: float,
    max_slope: float,
    slope_bins: tuple | list | None,
    extras: dict | None = None,
) -> list[tuple[str, str, str]]:
    """Driver rows as (driver_text, impact_text, kind) with kind positive|warn|neutral."""
    impact, kind = _driver_impact_for_mean(mean_slope)
    drivers: list[tuple[str, str, str]] = [
        (f"Mean slope {mean_slope:.1f}%", impact, kind),
    ]

    if slope_bins and len(slope_bins) >= 2:
        pct_below_25 = float(slope_bins[0])
        pct_below_5 = float(slope_bins[0]) + float(slope_bins[1])
        drivers.append((
            f"{pct_below_25:.1f}% of site below 2.5% slope",
            "Strong positive" if pct_below_25 >= 40 else "Moderate",
            "positive" if pct_below_25 >= 25 else "neutral",
        ))
        drivers.append((
            f"{pct_below_5:.1f}% of site below 5% slope",
            "Strong positive" if pct_below_5 >= 70 else "Moderate",
            "positive" if pct_below_5 >= 50 else "warn",
        ))

    ex = extras or {}
    if ex.get("cross_row_mean") is not None:
        cr_m = float(ex["cross_row_mean"])
        drivers.append((
            f"Mean cross-row slope {cr_m:.1f}%",
            "Tracker-friendly" if cr_m <= 3 else ("Review required" if cr_m > 4 else "Acceptable"),
            "positive" if cr_m <= 3 else ("warn" if cr_m > 4 else "neutral"),
        ))
    if ex.get("cross_row_p95") is not None:
        p95 = float(ex["cross_row_p95"])
        drivers.append((
            f"95th percentile cross-row {p95:.1f}%",
            "Tracker-friendly" if p95 <= 5 else "Review required",
            "positive" if p95 <= 5 else "warn",
        ))
    if ex.get("pct_cross_over_6") is not None:
        p6 = float(ex["pct_cross_over_6"])
        drivers.append((
            f"{p6:.1f}% area >6% cross-row",
            "Local grading zones" if p6 > 1 else "Within limits",
            "warn" if p6 > 1 else "positive",
        ))

    drivers.append((
        f"Maximum slope {max_slope:.1f}%",
        (
            "Small isolated areas"
            if max_slope > 8 and max_slope <= 15
            else "Steep constraint zones" if max_slope > 15 else "Within screening limits"
        ),
        "warn" if max_slope > 8 else "positive",
    ))
    return drivers


def build_terrain_verdict_why(
    mean_slope: float,
    verdict_fixed_label: str,
    verdict_tracker_label: str,
    extras: dict | None = None,
) -> list[tuple[str, str]]:
    """Bullet points for 'Why this verdict?' — (kind, text)."""
    bullets: list[tuple[str, str]] = []
    ex = extras or {}

    if mean_slope <= 10 and "Challenging" not in verdict_fixed_label:
        bullets.append(("positive", "Terrain suitable for utility-scale fixed tilt"))
    else:
        bullets.append(("warn", "Fixed-tilt layout may require significant earthworks"))

    if "Mostly Excellent" in verdict_tracker_label:
        bullets.append(("positive", "Terrain suitable for single-axis trackers"))
        bullets.append(("warn", "Localized tracker clearance review recommended"))
    elif "Excellent" in verdict_tracker_label or "Good" in verdict_tracker_label:
        bullets.append(("positive", "Terrain suitable for single-axis trackers"))
    elif "Moderate" in verdict_tracker_label:
        bullets.append(("warn", "Tracker deployment requires detailed civil study"))
    else:
        bullets.append(("warn", "Tracker layout likely constrained by terrain"))

    if mean_slope <= 5 and (ex.get("pct_cross_over_6") or 0) < 5:
        bullets.append(("positive", "Majority of site requires limited grading"))
    elif mean_slope <= 8:
        bullets.append(("warn", "Moderate grading expected across portions of site"))
    else:
        bullets.append(("warn", "Significant grading likely required"))

    bullets.append(("warn", "LiDAR survey required before FEED and pile design"))
    return bullets


def compute_terrain_drivers_summary(
    mean_slope: float,
    max_slope: float,
    slope_bins: tuple | list | None,
    extras: dict | None,
    verdict_fixed: tuple[str, str],
    verdict_tracker: tuple[str, str],
) -> dict:
    """Full Terrain Drivers block for UI and PDF."""
    score = calculate_terrain_score(mean_slope, max_slope, extras)
    label = get_terrain_score_label(score, verdict_tracker[0])
    return {
        "terrain_score": score,
        "terrain_score_label": label,
        "drivers": build_terrain_drivers(mean_slope, max_slope, slope_bins, extras),
        "why_bullets": build_terrain_verdict_why(
            mean_slope, verdict_fixed[0], verdict_tracker[0], extras,
        ),
    }


# ── Extended terrain analytics ───────────────────────────────────────────────

def _aspect_compass(deg: float) -> str:
    dirs = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    ix = int((deg + 22.5) % 360 / 45)
    return dirs[ix]


def _grid_resolution_label(grid_spacing: float, grid_spacing_requested: float | None = None) -> str:
    """Human-readable grid line for PDF/UI — avoids implying coarse spacing is default."""
    if grid_spacing_requested and grid_spacing > grid_spacing_requested + 0.5:
        return (
            f"{grid_spacing:.0f} m (coarsened from {grid_spacing_requested:.0f} m requested)"
        )
    return f"{grid_spacing:.0f} m"


def _grid_resolution_note(grid_spacing: float, grid_spacing_requested: float | None = None) -> str:
    """Footnote clarifying GLO-30 native limit vs output grid."""
    base = (
        "Public DEM native detail depends on source route; output grid is resampled for smoother "
        "slopes and CAD — not LiDAR-grade feature resolution."
    )
    if grid_spacing_requested and grid_spacing > grid_spacing_requested + 0.5:
        return (
            f"Auto-coarsened from {grid_spacing_requested:.0f} m for this boundary size. {base}"
        )
    if grid_spacing <= 5.5:
        return f"Default 5 m layout grid. {base}"
    return base


def _grid_limitations_text(grid_spacing: float, grid_spacing_requested: float | None = None) -> str:
    coarsened = grid_spacing_requested and grid_spacing > grid_spacing_requested + 0.5
    spacing_phrase = (
        f"resampled to {grid_spacing:.0f} m grid (coarsened from "
        f"{grid_spacing_requested:.0f} m — use 5 m for layout when possible)"
        if coarsened
        else f"resampled to {grid_spacing:.0f} m grid for layout and CAD export"
    )
    return (
        "<b>Screening limitations</b><br/>"
        f"Region-routed public DEM source ({spacing_phrase}). "
        "Typical vertical accuracy ±1–3 m RMSE. Vegetation and structures may bias slopes. "
        "Field survey (LiDAR/GNSS) required before detailed design and pile layout."
    )


def compute_terrain_extras(X, Y, Z, grid_m: float) -> dict:
    """
    Cross-row / along-row slope (N–S tracker rows) and dominant aspect.
    Rows assumed N–S (standard US practice); cross-row = E–W grade component.
    """
    out = {
        "cross_row_mean": None,
        "cross_row_p95": None,
        "along_row_mean": None,
        "pct_cross_over_3": None,
        "pct_cross_over_6": None,
        "dominant_aspect": None,
    }
    if not HAS_SCIPY:
        return out

    Zf = gaussian_filter(np.nan_to_num(Z, nan=np.nanmedian(Z[~np.isnan(Z)])), sigma=1)
    dz_dy, dz_dx = np.gradient(Zf, grid_m, grid_m)
    valid = ~np.isnan(Z)

    along = np.abs(dz_dy) * 100.0
    cross = np.abs(dz_dx) * 100.0
    a = along[valid]
    c = cross[valid]
    if len(c) == 0:
        return out

    out["along_row_mean"] = float(np.mean(a))
    out["cross_row_mean"] = float(np.mean(c))
    out["cross_row_p95"] = float(np.percentile(c, 95))
    out["pct_cross_over_3"] = float((c > 3).sum() / len(c) * 100)
    out["pct_cross_over_6"] = float((c > 6).sum() / len(c) * 100)

    asp = (np.degrees(np.arctan2(dz_dy, dz_dx)) + 360) % 360
    out["dominant_aspect"] = _aspect_compass(float(np.nanmedian(asp[valid])))
    return out


# ── Map rendering (basemap + slope + map elements) ─────────────────────────────

def _deg2tile(lat, lon, zoom):
    lat_r = math.radians(lat)
    n = 2.0 ** zoom
    x = int((lon + 180.0) / 360.0 * n)
    y = int((1.0 - math.log(math.tan(lat_r) + 1 / math.cos(lat_r)) / math.pi) / 2.0 * n)
    return x, y


def _tile2deg(x, y, zoom):
    n = 2.0 ** zoom
    lon = x / n * 360.0 - 180.0
    lat_r = math.atan(math.sinh(math.pi * (1 - 2 * y / n)))
    return math.degrees(lat_r), lon


def _fetch_imagery_mosaic(south, north, west, east, zoom=14):
    """Stitch Esri World Imagery tiles for bbox (best-effort)."""
    import requests
    from PIL import Image

    x_min, y_min = _deg2tile(north, west, zoom)
    x_max, y_max = _deg2tile(south, east, zoom)
    if (x_max - x_min + 1) * (y_max - y_min + 1) > 40:
        zoom -= 1
        x_min, y_min = _deg2tile(north, west, zoom)
        x_max, y_max = _deg2tile(south, east, zoom)
    rows = []
    lat_n = _tile2deg(x_min, y_min, zoom)[0]
    lat_s = _tile2deg(x_min, y_max + 1, zoom)[0]
    lon_w = _tile2deg(x_min, y_min, zoom)[1]
    lon_e = _tile2deg(x_max + 1, y_min, zoom)[1]
    url_tpl = (
        "https://server.arcgisonline.com/ArcGIS/rest/services/"
        "World_Imagery/MapServer/tile/{z}/{y}/{x}"
    )
    for ty in range(y_min, y_max + 1):
        row = []
        for tx in range(x_min, x_max + 1):
            try:
                r = requests.get(url_tpl.format(z=zoom, y=ty, x=tx), timeout=8)
                if r.status_code == 200:
                    row.append(np.array(Image.open(io.BytesIO(r.content)).convert("RGB")))
                else:
                    row.append(np.full((256, 256, 3), 200, dtype=np.uint8))
            except Exception:
                row.append(np.full((256, 256, 3), 200, dtype=np.uint8))
        rows.append(np.concatenate(row, axis=1))
    mosaic = np.concatenate(rows, axis=0)
    return mosaic, lat_n, lat_s, lon_w, lon_e


def render_slope_map_png(
    X, Y, Z, grid_m: float,
    south, north, west, east,
    polygon_list=None,
    terrain_source_used: str = "",
    terrain_disclaimer: str = "",
) -> Optional[io.BytesIO]:
    """Slope map with satellite basemap, north arrow, and scale bar (PDF-ready)."""
    if not HAS_SCIPY:
        return None
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.colors as mcolors
    from matplotlib.patches import Polygon as MplPoly

    dz_dy, dz_dx = np.gradient(
        gaussian_filter(np.nan_to_num(Z, nan=np.nanmedian(Z[~np.isnan(Z)])), sigma=1),
        grid_m, grid_m,
    )
    slope_pct = np.sqrt(dz_dx ** 2 + dz_dy ** 2) * 100.0
    slope_pct = np.where(np.isnan(Z), np.nan, slope_pct)
    Sm = np.ma.masked_invalid(slope_pct)

    fig, ax = plt.subplots(figsize=(10, 6.5))
    fig.patch.set_facecolor("#f5f7f5")
    ax.set_facecolor("#e8e8e8")

    # Basemap
    try:
        img, lat_n, lat_s, lon_w, lon_e = _fetch_imagery_mosaic(south, north, west, east)
        ax.imshow(
            img, extent=[lon_w, lon_e, lat_s, lat_n],
            aspect="auto", zorder=0, alpha=0.92,
        )
    except Exception:
        pass

    _slope_colors = [
        (0.000, "#1b5e20"), (0.167, "#388e3c"), (0.200, "#66bb6a"),
        (0.333, "#d4e157"), (0.500, "#ffa726"), (0.667, "#f44336"), (1.000, "#7f0000"),
    ]
    cmap_slope = mcolors.LinearSegmentedColormap.from_list(
        "solar_slope", [(p, c) for p, c in _slope_colors], N=512
    )
    lon_min, lon_max = float(np.nanmin(X)), float(np.nanmax(X))
    lat_min, lat_max = float(np.nanmin(Y)), float(np.nanmax(Y))
    im = ax.imshow(
        Sm, extent=[lon_min, lon_max, lat_min, lat_max],
        cmap=cmap_slope, vmin=0, vmax=15, alpha=0.55,
        interpolation="bilinear", aspect="auto", zorder=2,
    )

    if polygon_list:
        patches = []
        for coords in polygon_list:
            if coords and len(coords) >= 3:
                patches.append(MplPoly(
                    [(c[0], c[1]) for c in coords],
                    closed=True, fill=False, edgecolor="#ffffff", linewidth=1.2,
                ))
        if patches:
            from matplotlib.collections import PatchCollection
            ax.add_collection(PatchCollection(patches, match_original=True, zorder=3))

    cbar = fig.colorbar(im, ax=ax, fraction=0.035, pad=0.02)
    cbar.set_label("Slope (%)", fontsize=9)
    source_label = terrain_source_used.strip() or "Routed public DEM"
    ax.set_title(
        f"Slope map · {grid_m:.0f} m output grid · {source_label}  (green <3%, red >10%)",
        fontsize=11, fontweight="bold", color="#1a2e1a", pad=8,
    )
    ax.set_xlabel("Longitude", fontsize=8, color="#555")
    ax.set_ylabel("Latitude", fontsize=8, color="#555")
    ax.tick_params(labelsize=7)

    # North arrow — white, bold N beside shaft (upper-left)
    import matplotlib.patheffects as pe
    _stroke = [pe.withStroke(linewidth=3, foreground="#333333")]
    ax.text(
        0.034, 0.875, "N", transform=ax.transAxes, ha="center", va="center",
        fontsize=18, fontweight="bold", color="white", zorder=12,
        path_effects=_stroke,
    )
    ax.annotate(
        "", xy=(0.062, 0.955), xytext=(0.062, 0.795),
        xycoords="axes fraction",
        arrowprops=dict(
            arrowstyle="-|>", color="white", lw=4.5,
            mutation_scale=18, shrinkA=0, shrinkB=0,
        ),
        zorder=11,
    )

    # Scale bar (lower-right) — approximate metres at centre lat
    lat_c = (lat_min + lat_max) / 2
    m_per_deg_lon = 111320.0 * math.cos(math.radians(lat_c))
    span_m = (lon_max - lon_min) * m_per_deg_lon
    bar_m = 500 if span_m > 2000 else (200 if span_m > 800 else 100)
    bar_deg = bar_m / m_per_deg_lon
    x0 = lon_max - (lon_max - lon_min) * 0.28
    y0 = lat_min + (lat_max - lat_min) * 0.06
    ax.plot([x0, x0 + bar_deg], [y0, y0], color="#1a2e1a", linewidth=2.5, zorder=5)
    ax.text(x0 + bar_deg / 2, y0 + (lat_max - lat_min) * 0.02,
            f"{bar_m} m", ha="center", fontsize=7, color="#1a2e1a", zorder=5)

    plt.tight_layout(pad=0.6)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight", facecolor="#f5f7f5")
    plt.close(fig)
    buf.seek(0)
    return buf


# ── PDF report ─────────────────────────────────────────────────────────────────

def _verdict_color(vlabel: str):
    from reportlab.lib import colors
    if "Excellent" in vlabel:
        return colors.HexColor("#1b5e20")
    if "Good" in vlabel:
        return colors.HexColor("#2e7d32")
    if "Moderate" in vlabel:
        return colors.HexColor("#f57c00")
    return colors.HexColor("#c62828")


def _verdict_box(vlabel: str, vdetail: str, width, heading: str):
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph, Table, TableStyle
    from reportlab.lib.enums import TA_CENTER

    bg = _verdict_color(vlabel)
    t = Table([
        [Paragraph(f"<b>{heading}</b>", ParagraphStyle(
            "vh", fontName="Helvetica-Bold", fontSize=9,
            textColor=colors.white, alignment=TA_CENTER,
        ))],
        [Paragraph(f"<b>{vlabel}</b>", ParagraphStyle(
            "v1", fontName="Helvetica-Bold", fontSize=10,
            textColor=colors.white, alignment=TA_CENTER,
        ))],
        [Paragraph(vdetail, ParagraphStyle(
            "v2", fontSize=8, textColor=colors.white, alignment=TA_CENTER, leading=11,
        ))],
    ], colWidths=[width])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), bg),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ]))
    return t


def _lp(text, size=9, bold=False, color="#333333"):
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph
    from pvmath_geocode import pdf_escape

    fn = "Helvetica-Bold" if bold else "Helvetica"
    return Paragraph(pdf_escape(str(text)), ParagraphStyle(
        "lp", fontName=fn, fontSize=size, textColor=color, leading=size + 4,
        wordWrap="LTR",
    ))


def _img_flowable(buf, usable_w, max_ratio=0.72):
    from reportlab.platypus import Image as RLImage, Table, TableStyle
    from PIL import Image

    if not buf:
        return None
    buf.seek(0)
    img_h = usable_w * max_ratio
    try:
        im = Image.open(buf)
        iw, ih = im.size
        if iw > 0 and ih > 0:
            ratio = ih / iw
            if 0.2 <= ratio <= 1.4:
                img_h = usable_w * ratio
    except Exception:
        pass
    buf.seek(0)
    img = RLImage(buf, width=usable_w, height=img_h)
    tbl = Table([[img]], colWidths=[usable_w])
    tbl.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return tbl


def _impact_paragraph(text: str, kind: str):
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph

    if kind == "positive":
        col = colors.HexColor("#1b5e20")
        prefix = "+ "
    elif kind == "warn":
        col = colors.HexColor("#e65100")
        prefix = "! "
    else:
        col = colors.HexColor("#555555")
        prefix = ""
    return Paragraph(
        f"{prefix}{text}",
        ParagraphStyle("imp", fontName="Helvetica", fontSize=8.5, textColor=col, leading=12),
    )


def _append_terrain_drivers_section(story, ctx: dict, usable, hdr_style, body_style):
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.units import mm

    td = ctx.get("terrain_drivers") or {}
    if not td:
        return

    story.append(Spacer(1, 2 * mm))
    story.append(Paragraph("Terrain Drivers", hdr_style))
    story.append(Spacer(1, 1.5 * mm))
    story.append(Paragraph(
        f"<b>Terrain Score: {td['terrain_score']}/100 "
        f"({td['terrain_score_label']})</b>",
        ParagraphStyle(
            "tsc", parent=body_style, fontSize=11,
            fontName="Helvetica-Bold", leading=15,
        ),
    ))
    story.append(Spacer(1, 2 * mm))

    rows = [[_lp("Driver", bold=True, color="#ffffff"), _lp("Impact", bold=True, color="#ffffff")]]
    for driver, impact, kind in td.get("drivers", []):
        rows.append([_lp(driver, size=8.5), _impact_paragraph(impact, kind)])

    d_tbl = Table(rows, colWidths=[usable * 0.62, usable * 0.38])
    d_tbl.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1565c0")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f0f4f8")]),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#cccccc")),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story.append(d_tbl)
    story.append(Spacer(1, 3 * mm))

    story.append(Paragraph(
        "<b>Why this verdict?</b>",
        ParagraphStyle("whyh", parent=body_style, fontName="Helvetica-Bold", fontSize=9),
    ))
    story.append(Spacer(1, 1.5 * mm))
    for kind, text in td.get("why_bullets", []):
        if kind == "positive":
            icon, icol = "+", "#1b5e20"
        else:
            icon, icol = "!", "#e65100"
        story.append(Paragraph(
            f'<font color="{icol}"><b>{icon}</b></font>&nbsp;&nbsp;{text}',
            ParagraphStyle("whyb", parent=body_style, fontSize=8.5, leading=12, leftIndent=2),
        ))
        story.append(Spacer(1, 1.2 * mm))
    story.append(Spacer(1, 2 * mm))


def generate_pdf_report(ctx: dict) -> Optional[bytes]:
    """
    Build TerrainIQ terrain screening PDF from a context dict.
    See build_report_context() for expected keys.
    """
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors
        from reportlab.lib.units import mm
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
            Image as RLImage, HRFlowable, KeepTogether,
        )
        from reportlab.lib.enums import TA_CENTER, TA_LEFT
    except ImportError:
        return None

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        topMargin=14 * mm, bottomMargin=14 * mm,
        leftMargin=16 * mm, rightMargin=16 * mm,
    )
    W, _ = A4
    usable = W - 32 * mm

    MID_BLUE = colors.HexColor("#1565c0")
    DARK_BLUE = colors.HexColor("#0d2137")
    GREEN = colors.HexColor("#1b5e20")
    ORANGE = colors.HexColor("#f57c00")
    RED_C = colors.HexColor("#c62828")
    LIGHT_BG = colors.HexColor("#f0f4f8")
    MUTED = colors.HexColor("#666666")

    title_style = ParagraphStyle(
        "title", fontName="Helvetica-Bold", fontSize=13,
        textColor=colors.white, alignment=TA_LEFT, leading=16,
    )
    sub_style = ParagraphStyle(
        "sub", fontName="Helvetica", fontSize=8,
        textColor=colors.HexColor("#b0c4de"), alignment=TA_CENTER,
    )
    hdr_style = ParagraphStyle(
        "hdr", fontName="Helvetica-Bold", fontSize=10.5,
        textColor=MID_BLUE, spaceBefore=5, spaceAfter=3,
    )
    hdr_tight = ParagraphStyle(
        "hdr_t", parent=hdr_style, spaceBefore=0, spaceAfter=2,
    )
    body_style = ParagraphStyle(
        "body", fontName="Helvetica", fontSize=9,
        textColor=colors.HexColor("#333333"), leading=13,
    )
    cap_style = ParagraphStyle(
        "cap", fontName="Helvetica", fontSize=7.5,
        textColor=MUTED, alignment=TA_CENTER, leading=10,
    )

    story = []

    # ── Cover header ──────────────────────────────────────────────────────
    meta_right = (
        f"Report {ctx.get('report_id', '—')}<br/>"
        f"{ctx.get('generated_at', '')}<br/>"
        f"Rev {ctx.get('revision', 1)}"
    )
    header_tbl = Table([[
        Paragraph("TOPOIQ — TERRAIN SCREENING REPORT", title_style),
        Paragraph(meta_right, sub_style),
    ]], colWidths=["62%", "38%"])
    header_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), MID_BLUE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 11),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 11),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
    ]))
    story.append(header_tbl)

    tagline = ParagraphStyle(
        "tag", fontName="Helvetica-Oblique", fontSize=8,
        textColor=MUTED, alignment=TA_CENTER, spaceAfter=4,
    )
    story.append(Spacer(1, 2 * mm))
    story.append(Paragraph(
        "Preliminary terrain assessment for ground-mount solar — not a substitute for "
        "topographic survey, hydrology study, or geotechnical investigation.",
        tagline,
    ))
    story.append(Spacer(1, 3 * mm))

    # ── Screening limitations (prominent) ─────────────────────────────────
    lim = Table([[
        Paragraph(
            _grid_limitations_text(ctx["grid_spacing"], ctx.get("grid_spacing_requested")),
            ParagraphStyle("lim", fontSize=8, leading=11, textColor=DARK_BLUE),
        )
    ]], colWidths=[usable])
    lim.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#e3f2fd")),
        ("BOX", (0, 0), (-1, -1), 0.5, MID_BLUE),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(lim)
    story.append(Spacer(1, 4 * mm))

    # ── Project summary ───────────────────────────────────────────────────
    story.append(Paragraph("Project Summary", hdr_style))
    from pvmath_geocode import format_coords, resolve_location_label

    loc_line = resolve_location_label(
        ctx["lat_c"], ctx["lon_c"],
        saved_label=ctx.get("location_label", ""),
        country=ctx.get("country", ""),
    ) or "—"

    info_rows = []
    if ctx.get("project_name"):
        info_rows.append([
            _lp("Project", bold=True, color=DARK_BLUE),
            _lp(ctx["project_name"]),
        ])
    info_rows.append([
        _lp("Location", bold=True, color=DARK_BLUE),
        _lp(loc_line),
    ])
    info_rows.append([
        _lp("Coordinates", bold=True, color=DARK_BLUE),
        _lp(format_coords(ctx["lat_c"], ctx["lon_c"])),
    ])
    info_rows.append([
        _lp("Site area", bold=True, color=DARK_BLUE),
        _lp(f"{ctx['area_ha']:.1f} ha (union of enabled parcels)"),
    ])
    info_rows.append([
        _lp("Grid resolution", bold=True, color=DARK_BLUE),
        _lp(_grid_resolution_label(ctx["grid_spacing"], ctx.get("grid_spacing_requested"))),
    ])
    info_rows.append([
        _lp("Grid note", bold=True, color=DARK_BLUE),
        _lp(_grid_resolution_note(ctx["grid_spacing"], ctx.get("grid_spacing_requested"))),
    ])
    if ctx.get("boundary_provenance"):
        info_rows.append([
            _lp("Boundary source", bold=True, color=DARK_BLUE),
            _lp(ctx["boundary_provenance"]),
        ])
    if ctx.get("terrain_source_used"):
        info_rows.append([
            _lp("Terrain source route", bold=True, color=DARK_BLUE),
            _lp(
                f"{ctx['terrain_source_used']} ({(ctx.get('terrain_source') or {}).get('region', 'global')})"
            ),
        ])
    if (ctx.get("terrain_source") or {}).get("disclaimer"):
        info_rows.append([
            _lp("Terrain disclaimer", bold=True, color=DARK_BLUE),
            _lp((ctx.get("terrain_source") or {}).get("disclaimer")),
        ])
    if ctx.get("prepared_by"):
        info_rows.append([
            _lp("Prepared by", bold=True, color=DARK_BLUE),
            _lp(ctx["prepared_by"]),
        ])
    if ctx.get("module_confidence"):
        info_rows.append([
            _lp("Module confidence", bold=True, color=DARK_BLUE),
            _lp(ctx["module_confidence"]),
        ])

    label_w = 48 * mm
    info_tbl = Table(info_rows, colWidths=[label_w, usable - label_w])
    info_tbl.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BACKGROUND", (0, 0), (-1, -1), LIGHT_BG),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, LIGHT_BG]),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#cccccc")),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(info_tbl)
    story.append(Spacer(1, 4 * mm))

    # ── Slope map (KeepTogether) ──────────────────────────────────────────
    map_parts = [Paragraph("Slope Map", hdr_style)]
    slope_img = _img_flowable(ctx.get("slope_img_buf"), usable)
    if slope_img:
        map_parts.append(slope_img)
        map_parts.append(Spacer(1, 1.5 * mm))
        map_parts.append(Paragraph(
            "Figure 1 — Slope (%) over satellite basemap. Green &lt;3%, red &gt;10%. "
            "North arrow and scale bar shown.",
            cap_style,
        ))
    story.append(KeepTogether(map_parts))
    story.append(Spacer(1, 4 * mm))

    # ── Terrain metrics (honest rounding) ─────────────────────────────────
    z_min = round(ctx["z_min"])
    z_max = round(ctx["z_max"])
    z_rng = round(ctx["z_range"])
    mean_s = round(ctx["mean_slope"], 1)
    max_s = round(ctx["max_slope"], 1)
    p5 = round(ctx["pct_over5"], 1)
    p10 = round(ctx["pct_over10"], 1)
    ha5 = ctx.get("ha_over5", 0)
    ha10 = ctx.get("ha_over10", 0)

    metrics = [
        ["Parameter", "Value", "Notes"],
        ["Min elevation", f"{z_min} m", "Lowest grid point in boundary"],
        ["Max elevation", f"{z_max} m", "Highest grid point in boundary"],
        ["Elevation range", f"{z_rng} m", "Relief across site (DEM accuracy ±1–3 m)"],
        ["Mean slope", f"{mean_s}%", "Average gradient magnitude"],
        ["Max slope (point)", f"{max_s}%", "Steepest single grid cell"],
        ["Area > 5% slope", f"{p5}%", f"≈{ha5:.1f} ha · cumulative footprint above threshold"],
        ["Area > 10% slope", f"{p10}%", (
            f"≈{ha10:.1f} ha · max point {max_s}% may be a small sliver"
        )],
    ]
    m_tbl = Table(metrics, colWidths=[48 * mm, 28 * mm, usable - 76 * mm])
    m_tbl.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BACKGROUND", (0, 0), (-1, 0), MID_BLUE),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_BG]),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#cccccc")),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("ALIGN", (1, 1), (1, -1), "CENTER"),
    ]))
    story.append(KeepTogether([
        Paragraph("Terrain Metrics", hdr_tight),
        m_tbl,
    ]))
    story.append(Spacer(1, 4 * mm))

    # ── Phase B: slope direction ──────────────────────────────────────────
    ex = ctx.get("extras") or {}
    if ex.get("cross_row_mean") is not None:
        dir_rows = [
            ["Metric", "Value", "Notes"],
            ["Mean cross-row slope", f"{ex['cross_row_mean']:.1f}%",
             "E–W grade vs N–S tracker rows (screening assumption)"],
            ["95th %ile cross-row", f"{ex['cross_row_p95']:.1f}%",
             "Drives tracker ground clearance / backtracking risk"],
            ["Mean along-row slope", f"{ex['along_row_mean']:.1f}%",
             "Grade along row direction"],
            ["Area cross-row > 3%", f"{ex['pct_cross_over_3']:.1f}%", "Tracker excellent threshold"],
            ["Area cross-row > 6%", f"{ex['pct_cross_over_6']:.1f}%", "Tracker acceptable threshold"],
            ["Dominant aspect", ex.get("dominant_aspect", "—"),
             "Direction of steepest descent (median)"],
        ]
        d_tbl = Table(dir_rows, colWidths=[48 * mm, 28 * mm, usable - 76 * mm])
        d_tbl.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("BACKGROUND", (0, 0), (-1, 0), MID_BLUE),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_BG]),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#cccccc")),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(KeepTogether([
            Paragraph("Slope Direction (Tracker Screening)", hdr_tight),
            d_tbl,
        ]))
        story.append(Spacer(1, 4 * mm))

    # ── Slope distribution ────────────────────────────────────────────────
    slope_bins = ctx.get("slope_bins")
    if slope_bins:
        bin_labels = ["0% – 2.5%", "2.5% – 5%", "5% – 7.5%", "7.5% – 10%", "&gt; 10%"]
        bin_colors = [
            (colors.HexColor("#1b5e20"), colors.white),
            (colors.HexColor("#66bb6a"), colors.white),
            (colors.HexColor("#d4e157"), colors.HexColor("#1a1a1a")),
            (colors.HexColor("#ffa726"), colors.HexColor("#1a1a1a")),
            (colors.HexColor("#c62828"), colors.white),
        ]
        bins_data = [["Slope range", "% of site area"]]
        for lbl, pct in zip(bin_labels, slope_bins):
            bins_data.append([Paragraph(lbl, body_style), f"{round(pct, 1)}%"])
        bins_tbl = Table(bins_data, colWidths=[usable * 0.58, usable * 0.42])
        bs = [
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("BACKGROUND", (0, 0), (-1, 0), MID_BLUE),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#cccccc")),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("ALIGN", (1, 1), (1, -1), "CENTER"),
        ]
        for i, (bg, fg) in enumerate(bin_colors, start=1):
            bs.append(("BACKGROUND", (1, i), (1, i), bg))
            bs.append(("TEXTCOLOR", (1, i), (1, i), fg))
        bins_tbl.setStyle(TableStyle(bs))
        story.append(KeepTogether([
            Paragraph("Slope Distribution", hdr_tight),
            bins_tbl,
        ]))
        story.append(Spacer(1, 4 * mm))

    # ── Engineering verdict — fixed tilt & tracker side by side ─────────────
    story.append(Paragraph("Engineering Verdict", hdr_style))
    vf = ctx.get("verdict_fixed") or ("—", "")
    vt = ctx.get("verdict_tracker") or ("—", "")
    half = (usable - 4 * mm) / 2
    v_dual = Table([[
        _verdict_box(vf[0], vf[1], half, "Fixed Tilt"),
        _verdict_box(vt[0], vt[1], half, "Single-Axis Tracker"),
    ]], colWidths=[half, half])
    v_dual.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (0, 0), 0),
        ("RIGHTPADDING", (1, 0), (1, 0), 0),
    ]))
    story.append(v_dual)
    story.append(Spacer(1, 2 * mm))
    story.append(Paragraph(
        "<i>Both mounting systems assessed from the same DEM slope data. "
        "Cross-row metrics above apply to tracker screening.</i>",
        ParagraphStyle("vnote", fontSize=8, textColor=MUTED, leading=11),
    ))
    _append_terrain_drivers_section(story, ctx, usable, hdr_style, body_style)
    story.append(Spacer(1, 4 * mm))

    # Threshold tables
    story.append(Paragraph("Slope Threshold Reference", hdr_style))
    ft_data = [["Fixed tilt", "Threshold", "Interpretation"]] + list(FIXED_THRESHOLDS)
    tr_data = [["Single-axis tracker", "Threshold", "Interpretation"]] + list(TRACKER_THRESHOLDS)
    for label, rows in (("Fixed Tilt", ft_data), ("Tracker", tr_data)):
        t = Table(rows, colWidths=[usable * 0.28, usable * 0.18, usable * 0.54])
        t.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8eaf6")),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#cccccc")),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(t)
        story.append(Spacer(1, 2 * mm))

    # ── SiteIQ cross-reference ────────────────────────────────────────────
    if ctx.get("siteiq_note"):
        story.append(Spacer(1, 2 * mm))
        siq = Table([[
            Paragraph(
                f"<b>Companion site screening (SiteIQ)</b><br/>{ctx['siteiq_note']}",
                ParagraphStyle("siq", fontSize=8.5, leading=12, textColor=DARK_BLUE),
            )
        ]], colWidths=[usable])
        siq.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#e8f5ee")),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#1d9e52")),
            ("TOPPADDING", (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ]))
        story.append(siq)

    story.append(Spacer(1, 2 * mm))
    story.append(Paragraph(
        "<b>Recommended next step:</b> LiDAR or RTK survey before FEED and pile design.",
        ParagraphStyle("footer_note", fontSize=7.5, textColor=MUTED, leading=11),
    ))
    append_pdf_footer(
        story,
        "TerrainIQ",
        data_sources=(
            f"Region-routed free DEM source: {ctx.get('terrain_source_used', 'copernicus_glo30')}."
        ),
        note="Pre-survey terrain screening only — GLO-30 ~30 m native; output grid resampled for layout. Not a substitute for topographic survey or geotechnical investigation. ",
        muted_color=MUTED,
        border_color=colors.HexColor("#cccccc"),
    )

    doc.build(story)
    buf.seek(0)
    return buf.getvalue()


def build_report_context(
    *,
    project_name, country, location_label,
    lat_c, lon_c, area_ha, grid_spacing,
    grid_spacing_requested=None,
    z_min, z_max, mean_slope, max_slope,
    pct_over5, pct_over10,
    slope_bins, slope_img_buf,
    land_use, mount_type, boundary_provenance,
    prepared_by, extras,
    module_confidence: str = "",
    siteiq_run_cache=None,
    project_row_id=None,
    dem_zoom=None,
    terrain_source=None,
    terrain_source_used="copernicus_glo30",
    yield_cross_ref: str = "",
) -> dict:
    """Assemble all PDF fields from analysis outputs and project metadata."""
    mean_slope = float(mean_slope)
    z_range = float(z_max - z_min)
    ha_over5 = area_ha * pct_over5 / 100.0
    ha_over10 = area_ha * pct_over10 / 100.0
    ft_band = capacity_band(area_ha, land_use, "Fixed Tilt")
    tr_band = capacity_band(area_ha, land_use, "Single-Axis Tracker")

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    rid_suffix = (project_row_id or f"{lat_c:.3f}_{lon_c:.3f}")[:12]
    report_id = f"TQ-{rid_suffix}-{datetime.now(timezone.utc).strftime('%Y%m%d')}"

    verdict_fixed = _verdict_from_mean(mean_slope, "Fixed Tilt")
    verdict_tracker = verdict_for_mount(mean_slope, "Single-Axis Tracker", extras=extras)
    terrain_drivers = compute_terrain_drivers_summary(
        mean_slope, max_slope, slope_bins, extras,
        verdict_fixed, verdict_tracker,
    )

    siteiq_note = format_siteiq_companion_note(siteiq_run_cache)

    return {
        "project_name": project_name,
        "country": country,
        "location_label": location_label,
        "lat_c": lat_c,
        "lon_c": lon_c,
        "area_ha": area_ha,
        "grid_spacing": grid_spacing,
        "grid_spacing_requested": grid_spacing_requested,
        "z_min": z_min,
        "z_max": z_max,
        "z_range": z_range,
        "mean_slope": mean_slope,
        "max_slope": max_slope,
        "pct_over5": pct_over5,
        "pct_over10": pct_over10,
        "ha_over5": ha_over5,
        "ha_over10": ha_over10,
        "slope_bins": slope_bins,
        "slope_img_buf": slope_img_buf,
        "land_use": land_use,
        "mount_type": mount_type,
        "cap_ft_mwp": ft_band["mwp_lo"],
        "cap_ft_mwp_hi": ft_band["mwp_hi"],
        "cap_tr_mwp_lo": tr_band["mwp_lo"],
        "cap_tr_mwp_hi": tr_band["mwp_hi"],
        "density_ft": ft_band["dens_lo"],
        "density_ft_hi": ft_band["dens_hi"],
        "density_tr_lo": tr_band["dens_lo"],
        "density_tr_hi": tr_band["dens_hi"],
        "gcr_ft": ft_band["gcr_lo"],
        "gcr_ft_hi": ft_band["gcr_hi"],
        "gcr_tr_lo": tr_band["gcr_lo"],
        "gcr_tr_hi": tr_band["gcr_hi"],
        "dem_zoom": dem_zoom,
        "terrain_source": terrain_source or {},
        "terrain_source_used": terrain_source_used,
        "boundary_provenance": boundary_provenance,
        "prepared_by": prepared_by,
        "module_confidence": module_confidence,
        "extras": extras,
        "verdict_fixed": verdict_fixed,
        "verdict_tracker": verdict_tracker,
        "terrain_drivers": terrain_drivers,
        "report_id": report_id,
        "generated_at": ts,
        "revision": 1,
        "siteiq_note": siteiq_note,
        "yield_cross_ref": yield_cross_ref,
    }
