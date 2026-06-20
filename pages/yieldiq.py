"""
pages/yieldiq.py — YieldIQ: Pre-Layout Energy Yield Estimation
PVMath Platform · Module 03
Compares 4 configurations: 1P Fixed, 2P Fixed, 1P Tracker (SAT), 2P Tracker (SAT)
Data source: PVGIS JRC API (EU Commission)
"""

import re
import io
from datetime import date
from typing import Optional

import streamlit as st
import requests
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle,
    Paragraph, Spacer, HRFlowable, Image as RLImage,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

from pvmath_auth import (
    show_paywall, increment_usage, is_over_limit,
    remaining, FREE_LIMIT, UPGRADE_CONTACT,
    prepared_by_line, module_confidence_label,
)
from pvmath_styles import inject_styles
from pvmath_help import help_caption
from pvmath_capacity import (
    capacity_band_for_config,
    capacity_with_yield,
    format_mwp_range,
    format_mwh_range,
    format_density_range,
    capacity_all_configs_summary,
    capacity_footnote_global,
    GCR_REF,
    GCR_SCREEN_LO,
    GCR_SCREEN_HI,
)
from pvmath_geocode import format_coords
from pvmath_yield import (
    PVGIS_URL,
    CONFIG_ORDER,
    MONTHS,
    format_pvgis_total_loss,
    format_loss_pct,
    run_all_configs,
    fetch_screening_yields,
    yield_cross_ref_yieldiq_html,
    yield_cross_ref_yieldiq_pdf_text,
    config_display_name,
)

CHART_COLORS = ["#e85d04", "#c24a00", "#1d9e52", "#145f34"]  # Fixed: orange / Tracker: green

# ─────────────────────────────────────────────────────────────────────────────
# AUTH
# ─────────────────────────────────────────────────────────────────────────────
_uid = st.session_state.get("pvm_user_id", "guest")


# ─────────────────────────────────────────────────────────────────────────────
# CSS
# ─────────────────────────────────────────────────────────────────────────────
inject_styles(accent="#d4840a", accent_light="#fde8b0")

st.markdown("""
<style>
.yiq-section {
    font-size:1.05rem; font-weight:800; color:#b36a00;
    border-bottom:2.5px solid #fde8b0; padding-bottom:0.45rem;
    margin:1.6rem 0 0.9rem 0; letter-spacing:-0.01em;
}
.yiq-row {
    display:flex; align-items:center; padding:0.5rem 0;
    border-bottom:1px solid #f0f0ea;
}
.yiq-row-label {
    font-size:0.9rem; font-weight:700; color:#0d1a0d; flex:1;
}
.yiq-row-val {
    font-size:0.97rem; font-weight:800; color:#0d1a0d;
}
div[data-testid="metric-container"] {
    background:#fffbf4; border:1.5px solid #fde8b0;
    border-radius:12px; padding:1.1rem;
    box-shadow:0 1px 6px rgba(0,0,0,0.04);
}
div[data-testid="stTabs"] button[role="tab"][aria-selected="true"] {
    color:#d4840a !important; border-bottom-color:#d4840a !important; font-weight:800 !important;
}
div[data-testid="stTabs"] button[role="tab"] { font-weight:600 !important; color:#5a4a2a !important; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# HEADER
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("""
<div style="padding:1.5rem 0 0.5rem 0;border-bottom:2px solid #fef3e2;margin-bottom:1.5rem;">
  <div style="font-size:0.75rem;font-weight:700;text-transform:uppercase;
              letter-spacing:0.12em;color:#d4840a;margin-bottom:0.3rem;">Module 03</div>
  <h1 style="font-size:2rem;font-weight:800;color:#1a2e1a;margin:0 0 0.3rem 0;">YieldIQ ⚡</h1>
  <p style="color:#5a7a5a;font-size:1rem;margin:0;">
    Pre-layout energy yield estimation — 1P &amp; 2P · Fixed Tilt &amp; Single-Axis Tracker (SAT)
  </p>
</div>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# USAGE GATE
# ─────────────────────────────────────────────────────────────────────────────
if is_over_limit(_uid, "yieldiq"):
    show_paywall("YieldIQ")
    st.stop()

_left = remaining(_uid, "yieldiq")
if _left is not None and _left <= 2:
    st.warning(
        f"⚠️ {_left} free analysis{'es' if _left != 1 else ''} remaining on YieldIQ. "
        f"[Contact us to upgrade]({UPGRADE_CONTACT})"
    )

# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def parse_location(raw: str):
    """Return (lat, lon) or (None, None)."""
    raw = raw.strip()
    m = re.match(r"^(-?\d{1,3}\.?\d*)\s*,\s*(-?\d{1,3}\.?\d*)$", raw)
    if m:
        return float(m.group(1)), float(m.group(2))
    for pat in [
        r"@(-?\d+\.?\d+),(-?\d+\.?\d+)",
        r"[?&]q=(-?\d+\.?\d+),(-?\d+\.?\d+)",
        r"ll=(-?\d+\.?\d+),(-?\d+\.?\d+)",
        r"place/[^/]+/@(-?\d+\.?\d+),(-?\d+\.?\d+)",
    ]:
        m = re.search(pat, raw)
        if m:
            return float(m.group(1)), float(m.group(2))
    return None, None


# GCR shading, call_pvgis, run_all_configs → pvmath_yield.py (single source of truth)


def get_ghi(lat, lon, raddatabase=None) -> Optional[float]:
    """True horizontal-plane GHI (kWh/m²/yr) via PVGIS's PVcalc — the same
    endpoint already verified for spec_y/H(i)_y. Requesting a horizontal
    (angle=0) fixed plane makes H(i)_y equal GHI by definition, so this
    reuses proven parsing logic instead of an untested endpoint.
    """
    params = {
        "lat": round(lat, 5), "lon": round(lon, 5),
        "peakpower": 1, "loss": 14, "pvtechchoice": "crystSi",
        "mountingplace": "free", "outputformat": "json", "browser": 0,
        "fixed": 1, "angle": 0, "aspect": 0,
        "optimalinclination": 0, "optimalangles": 0,
    }
    if raddatabase:
        params["raddatabase"] = raddatabase
    try:
        resp = requests.get(
            PVGIS_URL, params=params, timeout=30,
            headers={"User-Agent": "YieldIQ/1.0 (pvmath.com; contact@pvmath.com)"}
        )
        resp.raise_for_status()
        data = resp.json()
        totals_d = data["outputs"].get("totals", {})
        key = "fixed" if "fixed" in totals_d else next(iter(totals_d), None)
        if not key:
            return None
        return round(float(totals_d[key].get("H(i)_y", 0)), 1)
    except Exception:
        return None


def get_dni_dhi(lat, lon, raddatabase=None, ghi_ref=None) -> tuple:
    """Annual DNI/DHI (kWh/m²/yr) via PVGIS MRcalc — climatological mean.

    MRcalc returns monthly rows for every year in the database (typically
    ~11 years × 12 months). Summing all rows without averaging would inflate
    annual totals by ~12× — the bug that produced DNI > 20,000 kWh/m²/yr.
    """
    params = {
        "lat": round(lat, 5), "lon": round(lon, 5),
        "horirrad": 1, "mr_dni": 1, "d2g": 1,
        "outputformat": "json",
    }
    if raddatabase:
        params["raddatabase"] = raddatabase
    try:
        resp = requests.get(
            "https://re.jrc.ec.europa.eu/api/v5_2/MRcalc", params=params, timeout=30,
            headers={"User-Agent": "YieldIQ/1.0 (pvmath.com; contact@pvmath.com)"}
        )
        resp.raise_for_status()
        monthly = resp.json()["outputs"].get("monthly", [])
        if not monthly:
            return None, None

        from collections import defaultdict
        by_month = defaultdict(lambda: {"h": [], "hb": [], "kd": []})
        for row in monthly:
            mo = row.get("month")
            if not mo:
                continue
            if "H(h)_m" in row:
                by_month[mo]["h"].append(float(row["H(h)_m"]))
            if "Hb(n)_m" in row:
                by_month[mo]["hb"].append(float(row["Hb(n)_m"]))
            for k in ("Kd", "d2g"):
                if k in row:
                    by_month[mo]["kd"].append(float(row[k]))

        if not by_month:
            return None, None

        dni = 0.0
        dhi = 0.0
        dni_ok = dhi_ok = False
        for mo in sorted(by_month):
            bucket = by_month[mo]
            if bucket["hb"]:
                dni += sum(bucket["hb"]) / len(bucket["hb"])
                dni_ok = True
            if bucket["h"] and bucket["kd"]:
                ghi_m = sum(bucket["h"]) / len(bucket["h"])
                kd_m = sum(bucket["kd"]) / len(bucket["kd"])
                dhi += ghi_m * kd_m
                dhi_ok = True

        dni = round(dni, 1) if dni_ok else None
        dhi = round(dhi, 1) if dhi_ok else None

        # Reject physically impossible combinations (bad parse / wrong units)
        if ghi_ref and dhi is not None and dhi > ghi_ref * 1.02:
            dhi = None
        if dni is not None and dni > 4000:
            dni = None
        if dhi is not None and ghi_ref and dhi > ghi_ref:
            dhi = None
        return dni, dhi
    except Exception:
        return None, None


def make_monthly_chart(results: dict, mwp_mid: float, title_cfg: str = "") -> bytes:
    """Grouped bar chart — monthly energy output (MWh) for all 4 configs."""
    x     = np.arange(12)
    width = 0.18
    fig, ax = plt.subplots(figsize=(13, 5))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("#f5f7f5")

    for i, (cfg, color) in enumerate(zip(CONFIG_ORDER, CHART_COLORS)):
        if cfg not in results:
            continue
        r = results[cfg]
        cfg_mwp = r.get("mwp_mid") or (
            (r.get("mwp_lo", 0) + r.get("mwp_hi", 0)) / 2 if r.get("mwp_lo") is not None else mwp_mid
        )
        vals_mwh = [v * cfg_mwp for v in results[cfg]["monthly"]]
        offset   = (i - 1.5) * width
        ax.bar(x + offset, vals_mwh, width, label=config_display_name(cfg), color=color,
               alpha=0.88, edgecolor="white", linewidth=0.5)

    ax.set_xlabel("Month", fontsize=10, labelpad=5, color="#5a7a5a")
    ax.set_ylabel("Energy output (MWh)", fontsize=10, labelpad=5, color="#5a7a5a")
    ax.set_xticks(x)
    ax.set_xticklabels(MONTHS, fontsize=9)
    ax.tick_params(axis="both", labelsize=9, colors="#5a7a5a")
    ax.legend(framealpha=0.9, fontsize=9, loc="upper left", ncol=2,
              edgecolor="#d4e0d4", labelcolor="#1a2e1a")
    ax.grid(axis="y", alpha=0.25, linewidth=0.5, color="#d4e0d4")
    ax.spines[["top", "right"]].set_visible(False)
    ax.spines[["left", "bottom"]].set_color("#d4e0d4")
    _title_r = results.get(title_cfg, {}) if title_cfg else {}
    _title_mwp = _title_r.get("mwp_mid") or (
        (_title_r.get("mwp_lo", 0) + _title_r.get("mwp_hi", 0)) / 2 if _title_r.get("mwp_lo") is not None else mwp_mid
    )
    ax.set_title(
        f"Monthly Energy Output — {_title_mwp:,.1f} MWp midpoint ({title_cfg or 'system'})",
        fontsize=11, fontweight="bold", pad=10, color="#1a2e1a"
    )
    plt.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    return buf.getvalue()


def build_pdf(project_name, lat, lon, area_ha, land_use, gcr_1p, gcr_2p,
              soiling_loss, other_loss, results, chart_bytes,
              best_mwh, best_cfg, ghi=None, dni=None, dhi=None,
              screening_note: str = "", cross_ref_text: str = "",
              prepared_by: str = "", module_confidence: str = "") -> bytes:
    """Generate ReportLab PDF report."""
    buf  = io.BytesIO()
    doc  = SimpleDocTemplate(buf, pagesize=A4,
                              leftMargin=2*cm, rightMargin=2*cm,
                              topMargin=2*cm,  bottomMargin=2*cm)
    styles = getSampleStyleSheet()
    S = lambda name, **kw: ParagraphStyle(name, parent=styles["Normal"], **kw)
    # ── Brand palette matching pvmath.com ─────────────────────────────────────
    AMBER    = colors.HexColor("#d4840a")
    AMBER_DK = colors.HexColor("#b36a00")
    GREEN_C  = colors.HexColor("#1d9e52")
    GREEN_DK = colors.HexColor("#145f34")
    DARK_TXT = colors.HexColor("#1a2e1a")
    MUTED    = colors.HexColor("#5a7a5a")
    LGRAY    = colors.HexColor("#f5f7f5")
    BORDER   = colors.HexColor("#d4e0d4")
    ORANGE_C = colors.HexColor("#e85d04")

    lbl  = S("lbl",  fontSize=7.5, fontName="Helvetica-Bold", textColor=MUTED)
    bod  = S("bod",  fontSize=9,   textColor=DARK_TXT, leading=13)
    sh   = S("sh",   fontSize=11,  fontName="Helvetica-Bold", textColor=DARK_TXT, spaceAfter=5)
    note = S("note", fontSize=7.5, textColor=colors.HexColor("#7a4f00"), leading=11)
    def lp(txt, style=bod): return Paragraph(str(txt), style)

    def section_hdr(text):
        t = Table([[
            Paragraph("", S("x")),
            Paragraph(text, S("sh2", fontSize=11, fontName="Helvetica-Bold", textColor=DARK_TXT, leading=14)),
        ]], colWidths=[0.28*cm, 16.72*cm])
        t.setStyle(TableStyle([
            ("BACKGROUND",    (0,0), (0,-1), AMBER),
            ("TOPPADDING",    (0,0), (-1,-1), 6),
            ("BOTTOMPADDING", (0,0), (-1,-1), 6),
            ("LEFTPADDING",   (1,0), (1,-1), 8),
            ("LEFTPADDING",   (0,0), (0,-1), 0),
            ("RIGHTPADDING",  (0,0), (-1,-1), 0),
        ]))
        return t

    story = []

    # ── Amber header bar (matches website mockup) ─────────────────────────────
    hdr = Table([[
        lp("YIELDIQ — ENERGY YIELD ESTIMATION REPORT",
           S("ht", fontSize=14, fontName="Helvetica-Bold", textColor=colors.white, leading=17)),
        lp("PVMath &nbsp;·&nbsp; pvmath.com",
           S("hs", fontSize=8.5, textColor=colors.HexColor("#fde8c0"), alignment=TA_RIGHT, leading=12)),
    ]], colWidths=["63%","37%"])
    hdr.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,-1), AMBER),
        ("VALIGN",        (0,0),(-1,-1), "MIDDLE"),
        ("TOPPADDING",    (0,0),(-1,-1), 13),
        ("BOTTOMPADDING", (0,0),(-1,-1), 13),
        ("LEFTPADDING",   (0,0),(-1,-1), 14),
        ("RIGHTPADDING",  (0,0),(-1,-1), 14),
    ]))
    story += [hdr, Spacer(1, 0.35*cm)]

    # ── Project info ──────────────────────────────────────────────────────────
    info_rows = [
        [lp("PROJECT",     lbl), lp(project_name, bod),
         lp("LOCATION",    lbl), lp(format_coords(lat, lon), bod)],
        [lp("SITE AREA",   lbl), lp(f"{area_ha:,.1f} ha" if area_ha else "—", bod),
         lp("LAND USE",    lbl), lp(land_use, bod)],
        [lp("GCR — 1P",   lbl), lp(f"{gcr_1p:.2f}", bod),
         lp("GCR — 2P",   lbl), lp(f"{gcr_2p:.2f}", bod)],
        [lp("SOILING / OTHER LOSSES", lbl), lp(f"{soiling_loss:.1f}% / {other_loss:.1f}% (excl. row shading)", bod),
         lp("DATE",        lbl), lp(str(date.today()), bod)],
        [lp("DATA SOURCE", lbl), lp("PVGIS JRC (EU Commission)", bod),
         lp("", lbl), lp("", bod)],
    ]
    if prepared_by:
        info_rows.append(
            [lp("PREPARED BY", lbl), lp(prepared_by, bod),
             lp("", lbl), lp("", bod)]
        )
    if module_confidence:
        info_rows.append(
            [lp("MODULE CONFIDENCE", lbl), lp(module_confidence, bod),
             lp("", lbl), lp("", bod)]
        )
    info = Table(info_rows, colWidths=[3*cm, 6*cm, 3*cm, 6*cm])
    info.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,-1), LGRAY),
        ("BOX",           (0,0),(-1,-1), 0.5, BORDER),
        ("TOPPADDING",    (0,0),(-1,-1), 5),
        ("BOTTOMPADDING", (0,0),(-1,-1), 5),
        ("LEFTPADDING",   (0,0),(-1,-1), 8),
    ]))
    story += [info, Spacer(1, 0.5*cm)]

    # ── Solar Resource ────────────────────────────────────────────────────────
    story.append(section_hdr("SOLAR RESOURCE"))
    story.append(Spacer(1, 0.15*cm))
    res_tbl_data = [
        [lp("GHI (Horizontal)", lbl), lp("DNI (Direct Normal)", lbl), lp("DHI (Diffuse Horizontal)", lbl)],
        [lp(f"{ghi:,.0f} kWh/m²/yr" if ghi else "—", bod),
         lp(f"{dni:,.0f} kWh/m²/yr" if dni else "—", bod),
         lp(f"{dhi:,.0f} kWh/m²/yr" if dhi else "—", bod)],
    ]
    resource_tbl = Table(res_tbl_data, colWidths=[5.57*cm, 5.57*cm, 5.57*cm])
    resource_tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,0), LGRAY),
        ("BOX",           (0,0),(-1,-1), 0.5, BORDER),
        ("INNERGRID",     (0,0),(-1,-1), 0.3, BORDER),
        ("TOPPADDING",    (0,0),(-1,-1), 6),
        ("BOTTOMPADDING", (0,0),(-1,-1), 6),
        ("LEFTPADDING",   (0,0),(-1,-1), 8),
    ]))
    story += [resource_tbl]
    if dni is None or dhi is None:
        story.append(Spacer(1, 0.1*cm))
        story.append(lp(
            "DNI/DHI not available for this location/response — shown as — rather than an "
            "unverified estimate. GHI is sourced from the same verified PVGIS endpoint used for "
            "the yield calculation below.", note
        ))
    else:
        story.append(Spacer(1, 0.1*cm))
        story.append(lp(
            "DNI/DHI from PVGIS MRcalc — monthly values averaged across all years in the "
            "database, then summed to an annual climatological mean. DHI is derived from "
            "horizontal irradiance × diffuse fraction (Kd); DHI ≤ GHI by definition.", note
        ))
    story.append(Spacer(1, 0.45*cm))

    # ── Performance (POA) ─────────────────────────────────────────────────────
    story.append(section_hdr("PERFORMANCE — PLANE-OF-ARRAY IRRADIANCE"))
    story.append(Spacer(1, 0.15*cm))
    _poa_fixed = results.get("1P Fixed", {}).get("h_y")
    _poa_track = results.get("1P Tracker", {}).get("h_y")
    perf_tbl = Table([
        [lp("POA — Fixed Tilt (1P)", lbl), lp("POA — Single-Axis Tracker (1P)", lbl)],
        [lp(f"{_poa_fixed:,.0f} kWh/m²/yr" if _poa_fixed else "—", bod),
         lp(f"{_poa_track:,.0f} kWh/m²/yr" if _poa_track else "—", bod)],
    ], colWidths=[8.36*cm, 8.36*cm])
    perf_tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,0), LGRAY),
        ("BOX",           (0,0),(-1,-1), 0.5, BORDER),
        ("INNERGRID",     (0,0),(-1,-1), 0.3, BORDER),
        ("TOPPADDING",    (0,0),(-1,-1), 6),
        ("BOTTOMPADDING", (0,0),(-1,-1), 6),
        ("LEFTPADDING",   (0,0),(-1,-1), 8),
    ]))
    story += [perf_tbl, Spacer(1, 0.45*cm)]

    # ── Losses Breakdown (best by annual energy) ─────────────────────────────
    if best_cfg and best_cfg in results:
        _b = results[best_cfg]
        story.append(section_hdr(f"LOSSES BREAKDOWN — {best_cfg} (BEST BY MWh/yr)"))
        story.append(Spacer(1, 0.15*cm))
        loss_tbl = Table([
            [lp("Shading", lbl), lp("Temperature", lbl), lp("Soiling", lbl), lp("Total Loss", lbl)],
            [lp(format_loss_pct(_b["shading"]), bod),
             lp(format_loss_pct(_b.get("l_tg")), bod),
             lp(format_loss_pct(_b["soiling_loss"]), bod),
             lp(format_pvgis_total_loss(_b), bod)],
        ], colWidths=[4.18*cm, 4.18*cm, 4.18*cm, 4.18*cm])
        loss_tbl.setStyle(TableStyle([
            ("BACKGROUND",    (0,0),(-1,0), LGRAY),
            ("BOX",           (0,0),(-1,-1), 0.5, BORDER),
            ("INNERGRID",     (0,0),(-1,-1), 0.3, BORDER),
            ("TOPPADDING",    (0,0),(-1,-1), 6),
            ("BOTTOMPADDING", (0,0),(-1,-1), 6),
            ("LEFTPADDING",   (0,0),(-1,-1), 8),
        ]))
        story += [loss_tbl, Spacer(1, 0.15*cm)]
        story.append(lp(
            "Temperature loss is PVGIS's own physics-based derate (not estimated). Total Loss is "
            "PVGIS's true combined figure where available (shading + soiling + other system losses "
            "+ temperature + angle-of-incidence + spectral).", note
        ))
        story.append(Spacer(1, 0.3*cm))

    # ── Results table ─────────────────────────────────────────────────────────
    story.append(section_hdr("RESULTS — CONFIGURATION COMPARISON"))
    story.append(Spacer(1, 0.15*cm))
    hdr_row = [lp(h, lbl) for h in [
        "Configuration","GCR\n(yield)","GCR\nband","MWp DC","Shading\nLoss","Total\nLoss",
        "POA Irrad.\n(kWh/m²/yr)","Specific Yield\n(kWh/kWp/yr)","Annual Energy\n(MWh/yr)","PR (%)","CF (%)"
    ]]
    rows = [hdr_row]
    _cfg_row_colors = []
    for cfg in CONFIG_ORDER:
        if cfg not in results:
            continue
        r  = results[cfg]
        is_best = cfg == best_cfg
        is_tracker = "Tracker" in cfg
        sy_color = GREEN_C if is_tracker else ORANGE_C
        sy_style = S("sy", fontSize=10, fontName="Helvetica-Bold", textColor=sy_color)
        cfg_style = S("cf", fontSize=9,
                      fontName="Helvetica-Bold" if is_best else "Helvetica",
                      textColor=GREEN_DK if is_tracker else colors.HexColor("#c24a00"))
        _mwp_txt = format_mwp_range(r.get("mwp_lo", 0), r.get("mwp_hi", 0))
        _mwh_txt = format_mwh_range(r.get("mwh_lo"), r.get("mwh_hi")) or "—"
        rows.append([
            lp(config_display_name(cfg) + (" ★" if is_best else ""), cfg_style),
            lp(f"{r['gcr']:.2f}", bod),
            lp(f"{GCR_SCREEN_LO:.2f}–{GCR_SCREEN_HI:.2f}", bod),
            lp(_mwp_txt, bod),
            lp(format_loss_pct(r["shading"]), bod),
            lp(format_pvgis_total_loss(r), bod),
            lp(f"{r['h_y']:,.0f}", bod),
            lp(f"{r['spec_y']:,.0f}", sy_style),
            lp(_mwh_txt, bod),
            lp(f"{r['pr']:.1f}%" if r["pr"] else "—", bod),
            lp(f"{r['cf']:.1f}%", bod),
        ])
        _cfg_row_colors.append(
            colors.HexColor("#f0faf4") if is_tracker else colors.HexColor("#fff4ee")
        )
    res_tbl = Table(rows, colWidths=[2.2*cm, 1.0*cm, 1.0*cm, 1.6*cm, 1.2*cm, 1.2*cm,
                                     1.5*cm, 2.0*cm, 1.8*cm, 1.0*cm, 1.0*cm])
    _tbl_style = [
        ("BACKGROUND",    (0,0),(-1, 0), AMBER),
        ("BOX",           (0,0),(-1,-1), 0.5, BORDER),
        ("INNERGRID",     (0,0),(-1,-1), 0.3, BORDER),
        ("VALIGN",        (0,0),(-1,-1), "MIDDLE"),
        ("TOPPADDING",    (0,0),(-1,-1), 6),
        ("BOTTOMPADDING", (0,0),(-1,-1), 6),
        ("LEFTPADDING",   (0,0),(-1,-1), 6),
    ]
    for _ri, _bg in enumerate(_cfg_row_colors):
        _tbl_style.append(("BACKGROUND", (0, _ri+1), (-1, _ri+1), _bg))
    res_tbl.setStyle(TableStyle(_tbl_style))
    story += [res_tbl]
    story.append(Spacer(1, 0.15*cm))
    story.append(lp(
        "Total Loss is PVGIS's combined l_total (soiling + other + shading input, plus temperature, "
        "angle-of-incidence, and spectral derates) — same figure as the Losses Breakdown box, "
        "not the user-input subtotal alone.",
        note,
    ))
    if screening_note:
        story.append(Spacer(1, 0.15*cm))
        story.append(lp(screening_note, note))
    if cross_ref_text:
        story.append(Spacer(1, 0.15*cm))
        story.append(lp(cross_ref_text, note))
    story.append(Spacer(1, 0.15*cm))
    story.append(lp(capacity_footnote_global(), note))
    story.append(Spacer(1, 0.35*cm))

    # ── Tracker gain summary ──────────────────────────────────────────────────
    gain_lines = []
    for pref in ["1P","2P"]:
        fix, trk = f"{pref} Fixed", f"{pref} Tracker"
        if fix in results and trk in results:
            g    = results[trk]["spec_y"] - results[fix]["spec_y"]
            gpct = g / results[fix]["spec_y"] * 100
            gain_lines.append(f"Tracker gain ({pref}): {g:+,.0f} kWh/kWp/yr ({gpct:+.1f}%) over Fixed Tilt")
    if gain_lines:
        story.append(lp(" | ".join(gain_lines), bod))
        story.append(Spacer(1, 0.4*cm))

    # ── Monthly chart ─────────────────────────────────────────────────────────
    story.append(section_hdr("MONTHLY ENERGY PROFILE"))
    story.append(Spacer(1, 0.15*cm))
    story.append(RLImage(io.BytesIO(chart_bytes), width=16*cm, height=6.5*cm))
    story.append(Spacer(1, 0.5*cm))

    # ── Disclaimer — amber warning box ───────────────────────────────────────
    disc_inner = Table([[
        lp("⚠  IMPORTANT DISCLAIMER", S("dt", fontSize=9, fontName="Helvetica-Bold",
                                         textColor=colors.HexColor("#7a4f00"), leading=12)),
    ]], colWidths=["100%"])
    disc_inner.setStyle(TableStyle([("LEFTPADDING",(0,0),(-1,-1),0),("BOTTOMPADDING",(0,0),(-1,-1),4)]))

    disc_body = (
        "These are preliminary yield estimates for pre-feasibility and internal go/no-go screening only. "
        "Results are based on PVGIS (EC JRC) satellite irradiance data and simplified row shading models derived from GCR. "
        "Typical uncertainty vs. a full bankable energy yield study: ±8–15%. "
        "PVMath does not claim bankability. "
        "A certified energy yield assessment (PVsyst + P50/P90 analysis by a qualified independent engineer) "
        "is required before financing, permitting, or EPC contract execution."
    )
    disc_tbl = Table([[
        lp(disc_body, S("db", fontSize=8.5, textColor=colors.HexColor("#7a4f00"), leading=13)),
    ]], colWidths=["100%"])
    disc_tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,-1), colors.HexColor("#fff8e6")),
        ("BOX",           (0,0),(-1,-1), 1.5, colors.HexColor("#f0b429")),
        ("TOPPADDING",    (0,0),(-1,-1), 10),
        ("BOTTOMPADDING", (0,0),(-1,-1), 10),
        ("LEFTPADDING",   (0,0),(-1,-1), 12),
        ("RIGHTPADDING",  (0,0),(-1,-1), 12),
    ]))
    story.append(disc_tbl)
    from pvmath_pdf import append_pdf_footer
    append_pdf_footer(
        story,
        "YieldIQ",
        data_sources="PVGIS JRC (EU Commission).",
        note="Pre-feasibility yield screening only — PVMath does not claim bankability. ",
        muted_color=MUTED,
        border_color=BORDER,
    )

    doc.build(story)
    buf.seek(0)
    return buf.read()


# ─────────────────────────────────────────────────────────────────────────────
# SHARED PROJECT CONTEXT
# ─────────────────────────────────────────────────────────────────────────────
_proj      = st.session_state.get("pvm_project", {})
_proj_lat  = _proj.get("lat")
_proj_lon  = _proj.get("lon")
_proj_name = _proj.get("name", "")
_proj_ctry = _proj.get("country", "")
_proj_area = _proj.get("area_ha")
_has_proj  = _proj_lat is not None and _proj_lon is not None

_CONFIG_CAPACITY = {
    "1P Fixed":   (False, False, "1p"),
    "2P Fixed":   (False, True,  "2p"),
    "1P Tracker": (True,  False, "1p"),
    "2P Tracker": (True,  True,  "2p"),
}


def attach_capacity(results: dict, area_ha: float, land_use: str) -> None:
    """Add screening-band MWp/MWh ranges to each config (in place)."""
    for cfg in _CONFIG_CAPACITY:
        if cfg not in results:
            continue
        band = capacity_band_for_config(area_ha, land_use, cfg)
        cap = capacity_with_yield(band, results[cfg]["spec_y"])
        results[cfg]["mwp_lo"] = band["mwp_lo"]
        results[cfg]["mwp_hi"] = band["mwp_hi"]
        results[cfg]["mwh_lo"] = cap["mwh_lo"]
        results[cfg]["mwh_hi"] = cap["mwh_hi"]
        results[cfg]["mwp_mid"] = (band["mwp_lo"] + band["mwp_hi"]) / 2
        results[cfg]["mwh_yr"] = (
            round(results[cfg]["spec_y"] * results[cfg]["mwp_mid"], 1) if area_ha else 0.0
        )

if _has_proj:
    st.markdown(f"""
    <div style="background:#e8f5ee;border:1px solid #b8ddc8;border-radius:8px;
                padding:0.65rem 1rem;margin-bottom:0.9rem;font-size:0.89rem;color:#1a3a1a;">
      <strong>📋 Project:</strong>&nbsp; {_proj_name}
      &nbsp;·&nbsp; {_proj_ctry}
      &nbsp;·&nbsp; {format_coords(_proj_lat, _proj_lon)}
      {f"&nbsp;·&nbsp; <strong>{_proj_area} ha</strong>" if _proj_area else ""}
    </div>
    """, unsafe_allow_html=True)
else:
    st.info(
        "💡 **Tip:** Set up a project in the **📋 Project** page to auto-fill location and name across all modules.",
        icon=None,
    )

# ── Land use for capacity density (all 4 configs run automatically) ─────────
_yiq_land_use = st.radio(
    "Land use",
    ["Standard", "Agri-PV"],
    index=0,
    horizontal=True,
    key="yiq_landuse",
    help="Affects MWp/ha for all four configurations. Mounting types are compared automatically.",
)
_area_ha = float(_proj_area) if _proj_area else 0.0

if not _has_proj:
    _area_ha = st.number_input(
        "Site Area (ha)", min_value=0.0, max_value=50_000.0,
        value=0.0, step=1.0,
        help="Required for MWp and MWh/yr. Set in Project page to auto-fill.",
    )

if _has_proj and _proj_area:
    st.markdown('<div class="yiq-section">📐 Site Capacity — All Configurations</div>',
                unsafe_allow_html=True)
elif _has_proj:
    st.info("Set site area in the **📋 Project** page to see capacity estimates.", icon=None)

_gcr_c1, _gcr_c2 = st.columns(2)
with _gcr_c1:
    gcr_1p = st.slider(
        "GCR for yield/shading model — 1-portrait", min_value=0.15, max_value=0.55,
        value=GCR_REF, step=0.01,
        help="Used for row-shading loss in the yield run only — not for MWp capacity (screening band GCR 0.30–0.42)."
    )
with _gcr_c2:
    gcr_2p = st.slider(
        "GCR for yield/shading model — 2-portrait", min_value=0.20, max_value=0.65,
        value=0.40, step=0.01,
        help="Used for row-shading loss in the yield run only — not for MWp capacity."
    )

if _area_ha and _area_ha > 0:
    _prev_hdr = st.columns([1.6, 0.9, 1.2, 1.2])
    for col, txt in zip(_prev_hdr, ["Configuration", "GCR band", "MWp DC", "MWp/ha eff."]):
        col.markdown(
            f"<div style='font-size:0.77rem;font-weight:700;color:#6a8a6a;"
            f"text-transform:uppercase;letter-spacing:0.04em;"
            f"border-bottom:1px solid #dde8dd;padding-bottom:4px;'>{txt}</div>",
            unsafe_allow_html=True,
        )
    for cfg in _CONFIG_CAPACITY:
        band = capacity_band_for_config(_area_ha, _yiq_land_use, cfg)
        _pr = st.columns([1.6, 0.9, 1.2, 1.2])
        _pr[0].markdown(f"**{config_display_name(cfg)}**")
        _pr[1].markdown(f"{GCR_SCREEN_LO:.2f}–{GCR_SCREEN_HI:.2f}")
        _pr[2].markdown(f"**{format_mwp_range(band['mwp_lo'], band['mwp_hi'])}**")
        _pr[3].markdown(format_density_range(
            band["dens_lo"], band["dens_hi"], band["gcr_lo"], band["gcr_hi"],
        ))

    st.markdown(
        '<div style="font-size:0.82rem;color:#7a6a2a;background:#fff8e1;'
        'border-left:3px solid #d4840a;border-radius:6px;padding:0.55rem 0.8rem;'
        'margin:0.5rem 0 0.9rem 0;">'
        '⚠️ <strong>MWp capacity uses the screening GCR band</strong> (0.30–0.42) — same as SiteIQ / TopoIQ. '
        'GCR sliders above affect row-shading in the yield model only. '
        '<strong>Best configuration = highest MWh/yr</strong> (midpoint MWp × specific yield).<br>'
        f'<span style="color:#5a4a2a;">{capacity_all_configs_summary(_area_ha, _yiq_land_use)}</span>'
        '</div>', unsafe_allow_html=True,
    )

# ─────────────────────────────────────────────────────────────────────────────
# INPUT FORM
# ─────────────────────────────────────────────────────────────────────────────
st.markdown('<div class="yiq-section">📍 Project Inputs</div>', unsafe_allow_html=True)

with st.form("yieldiq_form"):
    if _has_proj:
        st.markdown(
            f"**Site Location** — from Project: "
            f"`{format_coords(_proj_lat, _proj_lon)}`",
            help="Change site location in the Project page."
        )
        location_raw = ""
        c1_name = st.columns(1)[0]
        with c1_name:
            project_name = st.text_input(
                "Project Name", value=_proj_name, placeholder="e.g. Mannheim Solar 50 MWp"
            )
    else:
        c1, c2 = st.columns([1.4, 0.6])
        with c1:
            location_raw = st.text_input(
                "Site Location",
                placeholder="Paste coordinates (lat, lon) or a Google Maps URL",
                help="Right-click any point on Google Maps → 'What's here?' → copy the coordinates."
            )
        with c2:
            project_name = st.text_input(
                "Project Name", placeholder="e.g. Mannheim Solar 50 MWp"
            )

    c3, c4, c5 = st.columns(3)
    with c3:
        soiling_loss = st.number_input(
            "Soiling Loss (%)", min_value=0.0, max_value=10.0,
            value=2.0, step=0.5,
            help="Dust/dirt accumulation loss. Typical: 1–3% (temperate), 3–6% (arid/desert sites)."
        )
    with c4:
        other_loss = st.number_input(
            "Other System Losses (%)", min_value=3.0, max_value=20.0,
            value=6.0, step=0.5,
            help="Wiring, inverter, mismatch, availability — excludes row shading, soiling and "
                 "PVGIS's own temperature/AOI/spectral derates (those are computed automatically)."
        )
    with c5:
        st.markdown("<div style='height:1.85rem'></div>", unsafe_allow_html=True)
        submitted = st.form_submit_button(
            "⚡ Run Yield Analysis", use_container_width=True, type="primary"
        )

st.markdown("""
<div style="font-size:0.82rem;color:#7a8a7a;margin-top:0.4rem;">
Row shading losses are estimated from GCR using standard solar engineering approximations.
Tracker (SAT) shading modelled with backtracking — approx. 40 % of fixed-tilt shading at same GCR.
</div>
""", unsafe_allow_html=True)
help_caption("gcr", "shading_loss", "yield_screening")

# ─────────────────────────────────────────────────────────────────────────────
# RUN ANALYSIS
# ─────────────────────────────────────────────────────────────────────────────
if submitted:
    if _has_proj:
        lat, lon = _proj_lat, _proj_lon
    else:
        lat, lon = parse_location(location_raw)
        if lat is None:
            st.error("❌ Could not parse location. Paste coordinates as '48.137, 11.576' or a Google Maps URL.")
            st.stop()
        if not -90 <= lat <= 90 or not -180 <= lon <= 180:
            st.error("❌ Coordinates out of range. Check lat/lon order.")
            st.stop()
    if not project_name.strip():
        project_name = _proj_name or f"YieldIQ Site {lat:.3f}°, {lon:.3f}°"

    if is_over_limit(_uid, "yieldiq"):
        show_paywall("YieldIQ")
        st.stop()

    with st.spinner("Fetching PVGIS yield data for all 4 configurations…"):
        try:
            results, raddatabase = run_all_configs(lat, lon, gcr_1p, gcr_2p, soiling_loss, other_loss)
        except Exception as e:
            st.error(f"❌ PVGIS API error: {e}. Check coordinates or try again in a moment.")
            st.stop()

    with st.spinner("Fetching solar resource data (GHI/DNI/DHI)…"):
        ghi        = get_ghi(lat, lon, raddatabase=raddatabase)
        dni, dhi   = get_dni_dhi(lat, lon, raddatabase=raddatabase, ghi_ref=ghi)

    with st.spinner("Fetching SiteIQ screening reference for cross-check…"):
        _screening_yields = fetch_screening_yields(lat, lon, raddatabase)

    increment_usage(_uid, "yieldiq")

    _area_for_cap = float(_area_ha) if _area_ha and _area_ha > 0 else 0.0
    if _area_for_cap:
        attach_capacity(results, _area_for_cap, _yiq_land_use)
        _scr_note = capacity_all_configs_summary(_area_for_cap, _yiq_land_use)
        best_cfg = max(
            (c for c in CONFIG_ORDER if c in results),
            key=lambda c: results[c].get("mwh_yr", 0),
        )
        best_mwh = results[best_cfg]["mwh_yr"]
    else:
        _scr_note = ""
        best_cfg = max(
            (c for c in CONFIG_ORDER if c in results),
            key=lambda c: results[c]["spec_y"],
        )
        best_mwh = 0.0

    # ── Section: Solar Resource ────────────────────────────────────────────────
    st.markdown('<div class="yiq-section">🌞 Solar Resource</div>', unsafe_allow_html=True)
    res_cols = st.columns(3)
    res_cols[0].metric("GHI (Horizontal)", f"{ghi:,.0f} kWh/m²/yr" if ghi else "—")
    res_cols[1].metric("DNI (Direct Normal)", f"{dni:,.0f} kWh/m²/yr" if dni else "—")
    res_cols[2].metric("DHI (Diffuse Horizontal)", f"{dhi:,.0f} kWh/m²/yr" if dhi else "—")
    if dni is None or dhi is None:
        st.caption(
            "⚠️ DNI/DHI unavailable for this location/PVGIS response — shown as \"—\" rather than "
            "an unverified estimate. GHI is sourced from the same verified PVGIS endpoint as the "
            "yield calculation above."
        )

    # ── Section: Performance (POA) ─────────────────────────────────────────────
    st.markdown('<div class="yiq-section">📐 Performance — Plane-of-Array Irradiance</div>', unsafe_allow_html=True)
    perf_cols = st.columns(2)
    if "1P Fixed" in results:
        perf_cols[0].metric("POA — Fixed Tilt (1P)", f"{results['1P Fixed']['h_y']:,.0f} kWh/m²/yr")
    if "1P Tracker" in results:
        perf_cols[1].metric("POA — Single-Axis Tracker (1P)", f"{results['1P Tracker']['h_y']:,.0f} kWh/m²/yr")

    # ── Section: Losses Breakdown (for best-performing config) ────────────────
    st.markdown(
        f'<div class="yiq-section">📉 Losses Breakdown — {best_cfg} '
        f'({"best by MWh/yr" if _area_for_cap else "best by kWh/kWp"})</div>',
        unsafe_allow_html=True
    )
    _best = results[best_cfg]
    loss_cols = st.columns(4)
    loss_cols[0].metric("Shading", format_loss_pct(_best["shading"]))
    loss_cols[1].metric("Temperature", format_loss_pct(_best.get("l_tg")))
    loss_cols[2].metric("Soiling", format_loss_pct(_best["soiling_loss"]))
    loss_cols[3].metric(
        "Total Loss",
        format_pvgis_total_loss(_best),
    )
    st.caption(
        "Temperature loss is PVGIS's own physics-based derate (not estimated). "
        "Total Loss is PVGIS's true combined figure (shading + soiling + other system losses + "
        "temperature + angle-of-incidence + spectral) where available."
    )

    # ── Section: Results — Configuration Comparison ───────────────────────────
    st.markdown('<div class="yiq-section">📊 Results — Configuration Comparison</div>', unsafe_allow_html=True)

    # Column headers
    _COL_W = [1.4, 0.55, 0.75, 1.1, 0.9, 0.9, 1.0, 1.3, 1.3, 0.7, 0.7]
    hdr_cols = st.columns(_COL_W)
    for col, txt in zip(hdr_cols, [
        "Configuration","GCR\n(yield)","GCR\nband","MWp DC","Shading","Total Loss",
        "POA Irrad.","Specific Yield","Annual MWh","PR","CF"
    ]):
        col.markdown(
            f"<div style='font-size:0.77rem;font-weight:700;color:#6a8a6a;"
            f"text-transform:uppercase;letter-spacing:0.04em;"
            f"border-bottom:1px solid #dde8dd;padding-bottom:4px;'>{txt}</div>",
            unsafe_allow_html=True
        )

    for cfg in CONFIG_ORDER:
        if cfg not in results:
            continue
        r       = results[cfg]
        is_best = cfg == best_cfg
        best_badge = (' <span style="background:#e8f5e9;color:#2e7d32;font-size:0.62rem;'
                      'font-weight:700;padding:1px 7px;border-radius:10px;">BEST</span>'
                      if is_best else "")
        row_cols = st.columns(_COL_W)
        row_cols[0].markdown(
            f'<div style="padding:6px 0;font-weight:700;font-size:0.95rem;">'
            f'{config_display_name(cfg)}{best_badge}</div>', unsafe_allow_html=True)
        row_cols[1].markdown(
            f'<div style="padding:6px 0;color:#3a5a3a;">{r["gcr"]:.2f}</div>',
            unsafe_allow_html=True)
        row_cols[2].markdown(
            f'<div style="padding:6px 0;color:#6a8a6a;">{GCR_SCREEN_LO:.2f}–{GCR_SCREEN_HI:.2f}</div>',
            unsafe_allow_html=True)
        _mwp_txt = format_mwp_range(r.get("mwp_lo", 0), r.get("mwp_hi", 0))
        row_cols[3].markdown(
            f'<div style="padding:6px 0;font-weight:600;">'
            f'{_mwp_txt if r.get("mwp_lo") is not None else "—"}</div>',
            unsafe_allow_html=True)
        row_cols[4].markdown(
            f'<div style="padding:6px 0;color:#d4840a;font-weight:600;">{format_loss_pct(r["shading"])}</div>',
            unsafe_allow_html=True)
        row_cols[5].markdown(
            f'<div style="padding:6px 0;color:#5a7a5a;">{format_pvgis_total_loss(r)}</div>',
            unsafe_allow_html=True)
        row_cols[6].markdown(
            f'<div style="padding:6px 0;color:#3a5a3a;">{r["h_y"]:,.0f} kWh/m²</div>',
            unsafe_allow_html=True)
        row_cols[7].markdown(
            f'<div style="padding:6px 0;font-weight:700;color:#1565c0;font-size:1.05rem;">'
            f'{r["spec_y"]:,.0f} kWh/kWp</div>', unsafe_allow_html=True)
        _mwh_txt = format_mwh_range(r.get("mwh_lo"), r.get("mwh_hi"))
        row_cols[8].markdown(
            f'<div style="padding:6px 0;font-weight:600;">'
            f'{_mwh_txt if _mwh_txt else "— (set area)"}</div>',
            unsafe_allow_html=True)
        _pr_str = f'{r["pr"]:.1f}%' if r["pr"] else "—"
        row_cols[9].markdown(
            f'<div style="padding:6px 0;">{_pr_str}</div>',
            unsafe_allow_html=True)
        row_cols[10].markdown(
            f'<div style="padding:6px 0;">{r["cf"]:.1f}%</div>',
            unsafe_allow_html=True)

    st.caption(
        "Total Loss is PVGIS's combined figure (l_total): your soiling + other + shading input, "
        "plus PVGIS temperature, angle-of-incidence, and spectral derates — same value as the "
        "Losses Breakdown box above, not the user-input subtotal alone."
    )
    help_caption("specific_yield", "performance_ratio", "capacity_factor", "screening_grade")

    st.markdown(
        yield_cross_ref_yieldiq_html(
            _screening_yields, results, gcr_1p, soiling_loss, other_loss,
        ),
        unsafe_allow_html=True,
    )

    # ── Tracker gain (specific yield + energy where area known) ───────────────
    gain_cols = st.columns(2)
    for i, pref in enumerate(["1P", "2P"]):
        fix, trk = f"{pref} Fixed", f"{pref} Tracker"
        if fix in results and trk in results:
            g    = results[trk]["spec_y"] - results[fix]["spec_y"]
            gpct = g / results[fix]["spec_y"] * 100
            delta = ""
            if _area_for_cap:
                dmwh = results[trk].get("mwh_yr", 0) - results[fix].get("mwh_yr", 0)
                delta = f" · {dmwh:+,.0f} MWh/yr"
            gain_cols[i].metric(
                f"Tracker Gain ({pref})",
                f"{g:+,.0f} kWh/kWp/yr",
                f"{gpct:+.1f}% vs Fixed{delta}"
            )

    # ── Optimal tilt ──────────────────────────────────────────────────────────
    tilts = {c: results[c]["opt_tilt"]
             for c in ["1P Fixed","2P Fixed"]
             if c in results and results[c]["opt_tilt"] is not None}
    if tilts:
        tilt_str = "  |  ".join(f"{c}: **{int(t)}°**" for c, t in tilts.items())
        st.info(f"🔧 **Optimal tilt (PVGIS):** {tilt_str}")

    # ── Monthly chart ─────────────────────────────────────────────────────────
    st.markdown('<div class="yiq-section">📅 Monthly Energy Profile</div>', unsafe_allow_html=True)
    _chart_mwp = results[best_cfg].get("mwp_mid") or 1.0
    chart_bytes = make_monthly_chart(results, _chart_mwp, title_cfg=best_cfg)
    st.image(chart_bytes, use_container_width=True)

    # ── PDF download (generated once, shown immediately) ──────────────────────
    st.markdown("---")
    st.caption(module_confidence_label("yieldiq"))
    pdf_bytes = build_pdf(
        project_name, lat, lon, _area_for_cap, _yiq_land_use,
        gcr_1p, gcr_2p, soiling_loss, other_loss,
        results, chart_bytes, best_mwh, best_cfg, ghi, dni, dhi,
        screening_note=_scr_note,
        cross_ref_text=yield_cross_ref_yieldiq_pdf_text(_screening_yields, results),
        prepared_by=prepared_by_line(),
        module_confidence=module_confidence_label("yieldiq"),
    )
    safe_name = re.sub(r"[^\w\- ]", "", project_name).strip().replace(" ", "_")
    st.download_button(
        "📄 Download PDF Report",
        data=pdf_bytes,
        file_name=f"YieldIQ_{safe_name}.pdf",
        mime="application/pdf",
        type="primary",
    )

    # ── Disclaimer ────────────────────────────────────────────────────────────
    st.markdown("""
    <div style="margin-top:1rem;padding:0.8rem 1rem;background:#fff8e1;
                border-radius:8px;border-left:3px solid #d4840a;
                font-size:0.82rem;color:#7a6a2a;">
    <strong>Preliminary estimates only.</strong>
    Row shading losses are modelled from GCR using engineering approximations.
    Not a bankable energy yield assessment.
    A certified PVsyst or equivalent simulation is required for financing and EPC decisions.
    </div>
    """, unsafe_allow_html=True)
