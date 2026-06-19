"""TopoIQ terrain analytics, map rendering, and PDF report generation."""
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

# ── Capacity (aligned with SiteIQ) ───────────────────────────────────────────

def site_capacity_mw(area_ha: float, land_use: str = "Standard",
                     mount_type: str = "Fixed Tilt") -> tuple[float, str]:
    """Indicative AC capacity (MW) and density note for screening."""
    if land_use == "Agri-PV":
        density = 0.18 if mount_type == "Single-Axis Tracker" else 0.20
    else:
        density = 0.35 if mount_type == "Single-Axis Tracker" else 0.40
    mw = round(area_ha * density, 1)
    note = (
        f"{density:.2f} MW/ha screening density · {land_use} · {mount_type} "
        f"(not layout-optimised)"
    )
    return mw, note


def capacity_range_mw(area_ha: float, land_use: str = "Standard") -> str:
    """Show fixed-tilt and tracker range when mount not fixed."""
    ft, _ = site_capacity_mw(area_ha, land_use, "Fixed Tilt")
    tr, _ = site_capacity_mw(area_ha, land_use, "Single-Axis Tracker")
    return f"{tr:,.0f}–{ft:,.0f} MWac (tracker–fixed tilt range)"


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


# ── Extended terrain analytics ───────────────────────────────────────────────

def _aspect_compass(deg: float) -> str:
    dirs = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    ix = int((deg + 22.5) % 360 / 45)
    return dirs[ix]


def compute_terrain_extras(X, Y, Z, grid_m: float) -> dict:
    """
    Cross-row / along-row slope (N–S tracker rows), earthworks OOM, drainage hint.
  Rows assumed N–S (standard US practice); cross-row = E–W grade component.
    """
    out = {
        "cross_row_mean": None,
        "cross_row_p95": None,
        "along_row_mean": None,
        "pct_cross_over_3": None,
        "pct_cross_over_6": None,
        "dominant_aspect": None,
        "cut_m3": None,
        "fill_m3": None,
        "net_balance_m3": None,
        "depression_count": None,
        "drainage_direction": None,
    }
    if not HAS_SCIPY:
        return out

    Zf = gaussian_filter(np.nan_to_num(Z, nan=np.nanmedian(Z[~np.isnan(Z)])), sigma=1)
    dz_dy, dz_dx = np.gradient(Zf, grid_m, grid_m)
    valid = ~np.isnan(Z)

  # N–S rows: along-row ≈ |dz_dy|, cross-row ≈ |dz_dx|
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

    z_v = Z[valid]
    z_design = float(np.median(z_v))
    cell_m2 = grid_m * grid_m
    cut = np.maximum(Z[valid] - z_design, 0).sum() * cell_m2
    fill = np.maximum(z_design - Z[valid], 0).sum() * cell_m2
    out["cut_m3"] = round(float(cut), 0)
    out["fill_m3"] = round(float(fill), 0)
    out["net_balance_m3"] = round(float(cut - fill), 0)

    # Coarse D8 outflow toward site edges
    Zm = np.where(valid, Zf, np.nan)
    nr, nc = Zm.shape
    edge_flow = {"N": 0, "E": 0, "S": 0, "W": 0}
    depressions = 0
    for r in range(1, nr - 1):
        for c in range(1, nc - 1):
            if not valid[r, c]:
                continue
            z0 = Zm[r, c]
            neigh = []
            for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1),
                           (-1, -1), (-1, 1), (1, -1), (1, 1)):
                rr, cc = r + dr, c + dc
                if valid[rr, cc]:
                    neigh.append((Zm[rr, cc], dr, dc))
            if not neigh:
                continue
            lowest = min(neigh, key=lambda t: t[0])
            if lowest[0] >= z0 - 0.01:
                depressions += 1
                continue
            dr, dc = lowest[1], lowest[2]
            if dr < 0 and dc == 0:
                edge_flow["N"] += 1
            elif dr > 0 and dc == 0:
                edge_flow["S"] += 1
            elif dc > 0 and dr == 0:
                edge_flow["E"] += 1
            elif dc < 0 and dr == 0:
                edge_flow["W"] += 1
    out["depression_count"] = depressions
    if sum(edge_flow.values()) > 0:
        out["drainage_direction"] = max(edge_flow, key=edge_flow.get)
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
    ax.set_title(
        f"Slope map · {grid_m:.0f} m grid  (green <3%, red >10%)",
        fontsize=11, fontweight="bold", color="#1a2e1a", pad=8,
    )
    ax.set_xlabel("Longitude", fontsize=8, color="#555")
    ax.set_ylabel("Latitude", fontsize=8, color="#555")
    ax.tick_params(labelsize=7)

    # North arrow (upper-left)
    ax.annotate(
        "N", xy=(0.04, 0.92), xycoords="axes fraction",
        fontsize=11, fontweight="bold", color="#1a2e1a",
        ha="center",
    )
    ax.annotate(
        "", xy=(0.04, 0.96), xytext=(0.04, 0.88),
        xycoords="axes fraction",
        arrowprops=dict(arrowstyle="-|>", color="#1a2e1a", lw=1.5),
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


def render_drainage_map_png(X, Y, Z, grid_m: float) -> Optional[io.BytesIO]:
    """Simple flow-direction map for screening drainage patterns."""
    if not HAS_SCIPY:
        return None
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    valid = ~np.isnan(Z)
    Zf = gaussian_filter(np.nan_to_num(Z, nan=0), sigma=1)
    dz_dy, dz_dx = np.gradient(Zf, grid_m, grid_m)
    flow_ang = (np.degrees(np.arctan2(-dz_dy, -dz_dx)) + 360) % 360
    flow_ang = np.where(valid, flow_ang, np.nan)
    Fm = np.ma.masked_invalid(flow_ang)

    fig, ax = plt.subplots(figsize=(8, 5))
    fig.patch.set_facecolor("#f5f7f5")
    im = ax.imshow(Fm, cmap="hsv", vmin=0, vmax=360, aspect="auto")
    lon_min, lon_max = float(np.nanmin(X)), float(np.nanmax(X))
    lat_min, lat_max = float(np.nanmin(Y)), float(np.nanmax(Y))
    im.set_extent([lon_min, lon_max, lat_min, lat_max])
    cbar = fig.colorbar(im, ax=ax, fraction=0.04)
    cbar.set_label("Flow direction (°)", fontsize=8)
    ax.set_title("Indicative surface flow (screening only)", fontsize=10, fontweight="bold")
    ax.set_xlabel("Longitude", fontsize=8)
    ax.set_ylabel("Latitude", fontsize=8)
    plt.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120, bbox_inches="tight", facecolor="#f5f7f5")
    plt.close(fig)
    buf.seek(0)
    return buf


# ── PDF report ─────────────────────────────────────────────────────────────────

def _lp(text, size=9, bold=False, color="#333333"):
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph
    fn = "Helvetica-Bold" if bold else "Helvetica"
    return Paragraph(text, ParagraphStyle(
        "lp", fontName=fn, fontSize=size, textColor=color, leading=size + 4,
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


def generate_pdf_report(ctx: dict) -> Optional[bytes]:
    """
    Build TopoIQ terrain screening PDF from a context dict.
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
            "<b>Screening limitations</b><br/>"
            "Copernicus DEM GLO-30 (~30 m native), resampled to "
            f"{ctx['grid_spacing']:.0f} m grid. Typical vertical accuracy ±1–3 m RMSE. "
            "Vegetation and structures may bias slopes. Field survey (LiDAR/GNSS) "
            "required before detailed design and pile layout.",
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
    loc_line = ctx.get("location_label") or ctx.get("country") or "—"
    if ctx.get("country") and ctx.get("location_label"):
        loc_line = f"{ctx['location_label']}"

    info_rows = []
    if ctx.get("project_name"):
        info_rows.append(["Project", ctx["project_name"]])
    info_rows.append(["Location", loc_line])
    info_rows.append(["Coordinates", f"Lat {ctx['lat_c']:.5f}°, Lon {ctx['lon_c']:.5f}°"])
    info_rows.append([
        "Site area",
        f"{ctx['area_ha']:.1f} ha (union of enabled parcels)",
    ])
    info_rows.append(["Grid resolution", f"{ctx['grid_spacing']:.0f} m"])
    if ctx.get("boundary_provenance"):
        info_rows.append(["Boundary source", ctx["boundary_provenance"]])
    if ctx.get("land_use"):
        info_rows.append(["Land use", ctx["land_use"]])
    if ctx.get("mount_type"):
        info_rows.append(["Mounting system", ctx["mount_type"]])
    if ctx.get("cap_mw"):
        info_rows.append([
            "Indicative capacity",
            f"~{ctx['cap_mw']:,.0f} MWac — {ctx.get('cap_note', '')}",
        ])
    if ctx.get("prepared_by"):
        info_rows.append(["Prepared by", ctx["prepared_by"]])

    info_tbl = Table(info_rows, colWidths=[42 * mm, usable - 42 * mm])
    info_tbl.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 0), (0, -1), DARK_BLUE),
        ("BACKGROUND", (0, 0), (-1, -1), LIGHT_BG),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, LIGHT_BG]),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#cccccc")),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
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
    story.append(Paragraph("Terrain Metrics", hdr_style))
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
    story.append(m_tbl)
    story.append(Spacer(1, 4 * mm))

    # ── Phase B: slope direction ──────────────────────────────────────────
    ex = ctx.get("extras") or {}
    if ex.get("cross_row_mean") is not None:
        story.append(Paragraph("Slope Direction (Tracker Screening)", hdr_style))
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
        story.append(d_tbl)
        story.append(Spacer(1, 4 * mm))

    # ── Phase C: drainage + earthworks ────────────────────────────────────
    if ex.get("cut_m3") is not None:
        story.append(Paragraph("Drainage & Earthworks (Screening)", hdr_style))
        ew_rows = [
            ["Cut volume (est.)", f"{ex['cut_m3']:,.0f} m³",
             "vs median pad elevation — screening only"],
            ["Fill volume (est.)", f"{ex['fill_m3']:,.0f} m³", "Same design surface"],
            ["Net balance", f"{ex['net_balance_m3']:+,.0f} m³",
             "Positive = net cut; excludes roads, ponds, topsoil strip"],
            ["Local depressions", str(ex.get("depression_count", "—")),
             "Grid cells with no downslope neighbour (ponding risk)"],
            ["Dominant outflow", ex.get("drainage_direction") or "—",
             "Coarse surface flow toward site edge"],
        ]
        ew_tbl = Table(ew_rows, colWidths=[42 * mm, 32 * mm, usable - 74 * mm])
        ew_tbl.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("ROWBACKGROUNDS", (0, 0), (-1, -1), [LIGHT_BG, colors.white]),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#cccccc")),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(ew_tbl)
        story.append(Spacer(1, 2 * mm))
        drain_img = _img_flowable(ctx.get("drainage_img_buf"), usable * 0.85, 0.55)
        if drain_img:
            story.append(KeepTogether([
                Paragraph("Indicative Flow Map", hdr_style),
                drain_img,
                Paragraph(
                    "Figure 2 — Indicative surface flow from DEM gradient. "
                    "Not a hydrology model — confirm with civil engineer.",
                    cap_style,
                ),
            ]))
        story.append(Spacer(1, 4 * mm))

    # ── Slope distribution ────────────────────────────────────────────────
    slope_bins = ctx.get("slope_bins")
    if slope_bins:
        story.append(Paragraph("Slope Distribution", hdr_style))
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
        story.append(bins_tbl)
        story.append(Spacer(1, 4 * mm))

    # ── Engineering verdict (mount-aware) ─────────────────────────────────
    story.append(Paragraph("Engineering Verdict", hdr_style))
    mount = ctx.get("mount_type", "Fixed Tilt")
    vf = ctx.get("verdict_fixed") or ("—", "")
    vt = ctx.get("verdict_tracker") or ("—", "")
    primary = vt if mount == "Single-Axis Tracker" else vf
    vlabel, vdetail = primary

    if "Excellent" in vlabel:
        vcolor = GREEN
    elif "Good" in vlabel:
        vcolor = colors.HexColor("#2e7d32")
    elif "Moderate" in vlabel:
        vcolor = ORANGE
    else:
        vcolor = RED_C

    v_tbl = Table([
        [Paragraph(f"<b>{vlabel}</b>", ParagraphStyle(
            "v1", fontName="Helvetica-Bold", fontSize=11,
            textColor=colors.white, alignment=TA_CENTER,
        ))],
        [Paragraph(vdetail, ParagraphStyle(
            "v2", fontSize=9, textColor=colors.white, alignment=TA_CENTER,
        ))],
        [Paragraph(
            f"<i>Project mounting: {mount}. See threshold tables below for both systems.</i>",
            ParagraphStyle("v3", fontSize=8, textColor=colors.HexColor("#e8f5e9"),
                           alignment=TA_CENTER),
        )],
    ], colWidths=[usable])
    v_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), vcolor),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(v_tbl)
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

    story.append(Spacer(1, 4 * mm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#cccccc")))
    story.append(Spacer(1, 2 * mm))
    story.append(Paragraph(
        "<b>Data source:</b> Copernicus DEM GLO-30 (ESA/EC 2021) via AWS Terrain Tiles. "
        "Recommended next step: LiDAR or RTK survey before FEED and pile design.",
        ParagraphStyle("footer", fontSize=7.5, textColor=MUTED, leading=11),
    ))
    story.append(Paragraph(
        "Generated by TopoIQ · PVMath (pvmath.com) · contact@pvmath.com",
        ParagraphStyle("f2", fontName="Helvetica-Oblique", fontSize=7,
                       textColor=colors.HexColor("#999"), alignment=TA_CENTER),
    ))

    doc.build(story)
    buf.seek(0)
    return buf.getvalue()


def build_report_context(
    *,
    project_name, country, location_label,
    lat_c, lon_c, area_ha, grid_spacing,
    z_min, z_max, mean_slope, max_slope,
    pct_over5, pct_over10,
    slope_bins, slope_img_buf, drainage_img_buf,
    land_use, mount_type, boundary_provenance,
    prepared_by, extras,
    siteiq_run_cache=None,
    project_row_id=None,
) -> dict:
    """Assemble all PDF fields from analysis outputs and project metadata."""
    mean_slope = float(mean_slope)
    z_range = float(z_max - z_min)
    ha_over5 = area_ha * pct_over5 / 100.0
    ha_over10 = area_ha * pct_over10 / 100.0
    cap_mw, cap_note = site_capacity_mw(area_ha, land_use, mount_type)

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    rid_suffix = (project_row_id or f"{lat_c:.3f}_{lon_c:.3f}")[:12]
    report_id = f"TQ-{rid_suffix}-{datetime.now(timezone.utc).strftime('%Y%m%d')}"

    siteiq_note = (
        "Run SiteIQ on the same project for solar resource, flood risk, regulatory "
        "pathway, and overall site verdict. Terrain screening is one layer of the "
        "PVMath site intelligence workflow."
    )
    if siteiq_run_cache and siteiq_run_cache.get("solar"):
        siteiq_note = (
            "SiteIQ screening has been run on this project — open SiteIQ for the "
            "full report including solar resource, flood risk, regulatory pathway, "
            "and overall site verdict."
        )

    return {
        "project_name": project_name,
        "country": country,
        "location_label": location_label,
        "lat_c": lat_c,
        "lon_c": lon_c,
        "area_ha": area_ha,
        "grid_spacing": grid_spacing,
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
        "drainage_img_buf": drainage_img_buf,
        "land_use": land_use,
        "mount_type": mount_type,
        "cap_mw": cap_mw,
        "cap_note": cap_note,
        "boundary_provenance": boundary_provenance,
        "prepared_by": prepared_by,
        "extras": extras,
        "verdict_fixed": _verdict_from_mean(mean_slope, "Fixed Tilt"),
        "verdict_tracker": _verdict_from_mean(mean_slope, "Single-Axis Tracker"),
        "report_id": report_id,
        "generated_at": ts,
        "revision": 1,
        "siteiq_note": siteiq_note,
    }
