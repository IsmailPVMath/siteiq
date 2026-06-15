"""
pages/yieldiq.py — YieldIQ: Pre-Layout Energy Yield Estimation
PVMath Platform · Module 03
Compares 4 configurations: 1P Fixed, 2P Fixed, 1P Tracker (SAT), 2P Tracker (SAT)
Data source: PVGIS JRC API (EU Commission)
"""

import re
import io
import concurrent.futures
from datetime import date

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
    remaining, FREE_LIMIT, STRIPE_LINK, PRICE_LABEL,
)
from pvmath_styles import inject_styles

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
        f"[Upgrade — {PRICE_LABEL}]({STRIPE_LINK})"
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


# GCR → row shading loss (%) lookup table + linear interpolation
_GCR_TABLE = [
    (0.20, 0.3), (0.25, 0.5), (0.30, 1.0), (0.35, 2.0),
    (0.40, 3.5), (0.45, 5.5), (0.50, 8.0), (0.60, 12.0),
]

def gcr_shading(gcr: float, tracker: bool) -> float:
    """Shading loss (%) from GCR. Tracker uses backtracking → ~40 % of fixed shading."""
    if gcr <= _GCR_TABLE[0][0]:
        fs = _GCR_TABLE[0][1]
    elif gcr >= _GCR_TABLE[-1][0]:
        fs = _GCR_TABLE[-1][1]
    else:
        fs = _GCR_TABLE[0][1]
        for i in range(len(_GCR_TABLE) - 1):
            g0, s0 = _GCR_TABLE[i]
            g1, s1 = _GCR_TABLE[i + 1]
            if g0 <= gcr <= g1:
                t = (gcr - g0) / (g1 - g0)
                fs = s0 + t * (s1 - s0)
                break
    return round(fs * (0.40 if tracker else 1.0), 1)


PVGIS_URL = "https://re.jrc.ec.europa.eu/api/v5_2/PVcalc"
MONTHS    = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
CONFIG_ORDER  = ["1P Fixed", "2P Fixed", "1P Tracker", "2P Tracker"]
CHART_COLORS  = ["#e85d04", "#c24a00", "#1d9e52", "#145f34"]  # Fixed: orange / Tracker: green


def call_pvgis(lat: float, lon: float, total_loss_pct: float, tracker: bool) -> dict:
    """
    Call PVGIS PVcalc with peakpower=1 kWp.
    Returns specific yield (kWh/kWp/yr), monthly values, PR, CF, optimal tilt.
    """
    params = {
        "lat": round(lat, 5), "lon": round(lon, 5),
        "peakpower": 1,                    # always 1 → results = specific yield
        "loss": round(total_loss_pct, 1),
        "pvtechchoice": "crystSi",
        "mountingplace": "free",
        "outputformat": "json",
        "browser": 0,
        "trackingtype": 1 if tracker else 0,
    }
    if not tracker:
        params["optimalinclination"] = 1
        params["optimalangles"]      = 1

    resp = requests.get(
        PVGIS_URL, params=params, timeout=30,
        headers={"User-Agent": "YieldIQ/1.0 (pvmath.com; contact@pvmath.com)"}
    )
    resp.raise_for_status()
    data = resp.json()

    out        = data["outputs"]
    totals_d   = out.get("totals",  {})
    monthly_d  = out.get("monthly", {})

    # PVGIS always uses "fixed" as the key in PVcalc outputs regardless of tracking type
    key = "fixed" if "fixed" in totals_d else next(iter(totals_d), None)
    if not key:
        raise ValueError("Unexpected PVGIS response structure")

    tot          = totals_d[key]
    monthly_raw  = monthly_d.get(key, [])

    # E_y and E_m are in kWh (PVGIS v5.2, peakpower=1 kWp)
    spec_y    = float(tot.get("E_y", 0))                    # kWh/kWp/yr
    h_y       = float(tot.get("H(i)_y", 0))                 # kWh/m²/yr in-plane
    monthly   = [float(m.get("E_m", 0)) for m in monthly_raw]  # kWh/kWp/month × 12

    pr = round(spec_y / h_y * 100, 1) if h_y else None
    cf = round(spec_y / 8760 * 100,  1)

    # Optimal tilt (fixed only)
    opt_tilt = None
    if not tracker:
        meta  = data.get("meta", {})
        slope = meta.get("slope", {})
        if isinstance(slope, dict):
            v = slope.get("value")
            opt_tilt = float(v) if v is not None else None
        elif isinstance(slope, (int, float)):
            opt_tilt = float(slope)

    return {
        "spec_y":   round(spec_y, 0),
        "monthly":  [round(x, 1) for x in monthly],
        "h_y":      round(h_y, 1),
        "pr":       pr,
        "cf":       cf,
        "opt_tilt": opt_tilt,
    }


def run_all_configs(lat, lon, gcr_1p, gcr_2p, base_loss):
    """Run 4 PVGIS calls concurrently. Returns dict keyed by config name."""
    cfg_params = {
        "1P Fixed":   (gcr_1p, False),
        "2P Fixed":   (gcr_2p, False),
        "1P Tracker": (gcr_1p, True),
        "2P Tracker": (gcr_2p, True),
    }

    def _call(name, gcr, tracker):
        shade      = gcr_shading(gcr, tracker)
        total_loss = min(base_loss + shade, 30.0)
        res = call_pvgis(lat, lon, total_loss, tracker)
        res["gcr"]        = gcr
        res["shading"]    = shade
        res["total_loss"] = round(total_loss, 1)
        res["tracker"]    = tracker
        return name, res

    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
        futs = {ex.submit(_call, n, g, t): n for n, (g, t) in cfg_params.items()}
        for fut in concurrent.futures.as_completed(futs):
            name, res = fut.result()
            results[name] = res
    return results


def make_monthly_chart(results: dict, dc_kwp: float) -> bytes:
    """Grouped bar chart — monthly energy output (MWh) for all 4 configs."""
    x     = np.arange(12)
    width = 0.18
    fig, ax = plt.subplots(figsize=(13, 5))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("#f5f7f5")

    for i, (cfg, color) in enumerate(zip(CONFIG_ORDER, CHART_COLORS)):
        if cfg not in results:
            continue
        vals_mwh = [v * dc_kwp / 1000 for v in results[cfg]["monthly"]]
        offset   = (i - 1.5) * width
        ax.bar(x + offset, vals_mwh, width, label=cfg, color=color,
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
    ax.set_title(
        f"Monthly Energy Output — {dc_kwp:,.0f} kWp System",
        fontsize=11, fontweight="bold", pad=10, color="#1a2e1a"
    )
    plt.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    return buf.getvalue()


def build_pdf(project_name, lat, lon, dc_kwp, gcr_1p, gcr_2p, base_loss,
              results, chart_bytes, best_sy) -> bytes:
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
    info = Table([
        [lp("PROJECT",     lbl), lp(project_name, bod),
         lp("LOCATION",    lbl), lp(f"{lat:.5f}°N, {lon:.5f}°E", bod)],
        [lp("DC CAPACITY", lbl), lp(f"{dc_kwp:,.0f} kWp", bod),
         lp("DATE",        lbl), lp(str(date.today()), bod)],
        [lp("GCR — 1P",   lbl), lp(f"{gcr_1p:.2f}", bod),
         lp("GCR — 2P",   lbl), lp(f"{gcr_2p:.2f}", bod)],
        [lp("BASE LOSSES", lbl), lp(f"{base_loss:.1f}% (excl. row shading)", bod),
         lp("DATA SOURCE", lbl), lp("PVGIS JRC (EU Commission)", bod)],
    ], colWidths=["3cm","6cm","3cm","6cm"])
    info.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,-1), LGRAY),
        ("BOX",           (0,0),(-1,-1), 0.5, BORDER),
        ("TOPPADDING",    (0,0),(-1,-1), 5),
        ("BOTTOMPADDING", (0,0),(-1,-1), 5),
        ("LEFTPADDING",   (0,0),(-1,-1), 8),
    ]))
    story += [info, Spacer(1, 0.5*cm)]

    # ── Results table ─────────────────────────────────────────────────────────
    story.append(section_hdr("CONFIGURATION COMPARISON"))
    story.append(Spacer(1, 0.15*cm))
    hdr_row = [lp(h, lbl) for h in [
        "Configuration","GCR","Shading\nLoss","Total\nLoss",
        "Specific Yield\n(kWh/kWp/yr)","Annual Energy\n(MWh/yr)","PR (%)","CF (%)"
    ]]
    rows = [hdr_row]
    _cfg_row_colors = []  # track row background per cfg
    for cfg in CONFIG_ORDER:
        if cfg not in results:
            continue
        r  = results[cfg]
        is_best = r["spec_y"] == best_sy
        is_tracker = "Tracker" in cfg
        sy_color = GREEN_C if is_tracker else ORANGE_C
        sy_style = S("sy", fontSize=10, fontName="Helvetica-Bold", textColor=sy_color)
        cfg_style = S("cf", fontSize=9,
                      fontName="Helvetica-Bold" if is_best else "Helvetica",
                      textColor=GREEN_DK if is_tracker else colors.HexColor("#c24a00"))
        rows.append([
            lp(cfg + (" ★" if is_best else ""), cfg_style),
            lp(f"{r['gcr']:.2f}", bod),
            lp(f"{r['shading']:.1f}%", bod),
            lp(f"{r['total_loss']:.1f}%", bod),
            lp(f"{r['spec_y']:,.0f}", sy_style),
            lp(f"{r['spec_y'] * dc_kwp / 1000:,.1f}", bod),
            lp(f"{r['pr']:.1f}%" if r["pr"] else "—", bod),
            lp(f"{r['cf']:.1f}%", bod),
        ])
        _cfg_row_colors.append(
            colors.HexColor("#f0faf4") if is_tracker else colors.HexColor("#fff4ee")
        )
    res_tbl = Table(rows, colWidths=["3cm","1.4cm","1.7cm","1.7cm","3cm","2.8cm","1.5cm","1.5cm"])
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
    story += [res_tbl, Spacer(1, 0.5*cm)]

    # ── Tracker gain summary ──────────────────────────────────────────────────
    gain_lines = []
    for pref in ["1P","2P"]:
        fix, trk = f"{pref} Fixed", f"{pref} Tracker"
        if fix in results and trk in results:
            g    = results[trk]["spec_y"] - results[fix]["spec_y"]
            gpct = g / results[fix]["spec_y"] * 100
            gain_lines.append(f"Tracker gain ({pref}): +{g:,.0f} kWh/kWp/yr (+{gpct:.1f}%) over Fixed Tilt")
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
    story.append(Spacer(1, 0.3*cm))
    story.append(HRFlowable(width="100%", thickness=1, color=BORDER))
    story.append(Spacer(1, 0.2*cm))
    story.append(lp(
        "Generated by YieldIQ — PVMath Solar Site Intelligence Platform &nbsp;|&nbsp; pvmath.com &nbsp;|&nbsp; "
        "Data: PVGIS JRC (EU Commission). For professional use only.",
        S("ft", fontSize=7, textColor=MUTED, leading=10)))

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
_has_proj  = bool(_proj_lat and _proj_lon)

# Capacity density table (MW/ha)
_DENSITY = {
    ("Standard",  "Fixed Tilt"):          0.40,
    ("Standard",  "Single-Axis Tracker"): 0.35,
    ("Agri-PV",   "Fixed Tilt"):          0.20,
    ("Agri-PV",   "Single-Axis Tracker"): 0.18,
}

if _has_proj:
    st.markdown(f"""
    <div style="background:#e8f5ee;border:1px solid #b8ddc8;border-radius:8px;
                padding:0.65rem 1rem;margin-bottom:0.9rem;font-size:0.89rem;color:#1a3a1a;">
      <strong>📋 Project:</strong>&nbsp; {_proj_name}
      &nbsp;·&nbsp; {_proj_ctry}
      &nbsp;·&nbsp; {_proj_lat:.5f}°N, {_proj_lon:.5f}°E
      {f"&nbsp;·&nbsp; <strong>{_proj_area} ha</strong>" if _proj_area else ""}
    </div>
    """, unsafe_allow_html=True)
else:
    st.info(
        "💡 **Tip:** Set up a project in the **📋 Project** page to auto-fill location and name across all modules.",
        icon=None,
    )

# ── Capacity scenario selector (shown when project area is known) ─────────────
_default_dc_kwp = 10_000.0
_scenario_label = "Custom"

if _has_proj and _proj_area:
    st.markdown('<div class="yiq-section">📐 Site Capacity — 4 Scenarios for Your Area</div>',
                unsafe_allow_html=True)

    _scenarios = []
    for (lu, mt), dens in _DENSITY.items():
        _mwp = round(_proj_area * dens, 1)
        _scenarios.append({
            "label":   f"{lu} · {mt}",
            "land_use": lu, "mount": mt,
            "density": dens,
            "mwp":     _mwp,
            "kwp":     _mwp * 1000,
        })

    # Show table of 4 scenarios
    _col_h = ["Scenario", "Land Use", "Mounting", "Density (MW/ha)", f"Est. Capacity for {_proj_area} ha"]
    _tbl_data = [_col_h] + [
        [f"{'⭐ ' if i==0 else ''}{s['label']}",
         s["land_use"], s["mount"],
         f"{s['density']} MW/ha",
         f"**{s['mwp']} MWp**"]
        for i, s in enumerate(_scenarios)
    ]

    st.markdown(f"""
    <table style="width:100%;border-collapse:collapse;font-size:0.88rem;margin-bottom:1rem;">
      <thead>
        <tr style="background:#145f34;color:#fff;">
          {''.join(f'<th style="padding:0.5rem 0.7rem;text-align:left;">{h}</th>' for h in _col_h)}
        </tr>
      </thead>
      <tbody>
        {''.join(
          f'<tr style="background:{"#f0faf5" if i%2==0 else "#fff"};{"border:2px solid #1d9e52;" if i==0 else ""}">'
          + f'<td style="padding:0.45rem 0.7rem;font-weight:700;color:#145f34;">{s["label"]}</td>'
          + f'<td style="padding:0.45rem 0.7rem;">{s["land_use"]}</td>'
          + f'<td style="padding:0.45rem 0.7rem;">{s["mount"]}</td>'
          + f'<td style="padding:0.45rem 0.7rem;text-align:center;">{s["density"]}</td>'
          + f'<td style="padding:0.45rem 0.7rem;font-weight:800;font-size:1rem;color:#0d5c0d;">{s["mwp"]} MWp</td>'
          + '</tr>'
          for i, s in enumerate(_scenarios)
        )}
      </tbody>
    </table>
    """, unsafe_allow_html=True)

    _scenario_options = [f"{s['label']} — {s['mwp']} MWp" for s in _scenarios] + ["Custom value"]
    _sel = st.selectbox("Use capacity from scenario:", _scenario_options, index=0,
                        key="yiq_scenario_sel",
                        help="Select a scenario to auto-fill the DC capacity below, or enter a custom value.")
    if _sel != "Custom value":
        _idx = _scenario_options.index(_sel)
        _default_dc_kwp = _scenarios[_idx]["kwp"]
        _scenario_label = _sel
    else:
        _default_dc_kwp = 10_000.0

# ─────────────────────────────────────────────────────────────────────────────
# INPUT FORM
# ─────────────────────────────────────────────────────────────────────────────
st.markdown('<div class="yiq-section">📍 Project Inputs</div>', unsafe_allow_html=True)

with st.form("yieldiq_form"):
    if _has_proj:
        st.markdown(
            f"**Site Location** — from Project: "
            f"`{_proj_lat:.5f}°N, {_proj_lon:.5f}°E`",
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

    c3, c4, c5, c6, c7 = st.columns(5)
    with c3:
        dc_kwp = st.number_input(
            "Target DC Capacity (kWp)", min_value=1.0, max_value=5_000_000.0,
            value=float(_default_dc_kwp), step=500.0,
            help="Total rated DC power of the system. Auto-filled from scenario above."
        )
    with c4:
        gcr_1p = st.number_input(
            "GCR — 1P", min_value=0.15, max_value=0.55,
            value=0.28, step=0.01, format="%.2f",
            help="Ground Cover Ratio for 1-portrait configurations. Typical: 0.25–0.33"
        )
    with c5:
        gcr_2p = st.number_input(
            "GCR — 2P", min_value=0.20, max_value=0.65,
            value=0.40, step=0.01, format="%.2f",
            help="Ground Cover Ratio for 2-portrait configurations. Typical: 0.35–0.50"
        )
    with c6:
        base_loss = st.number_input(
            "Base Losses (%)", min_value=5.0, max_value=25.0,
            value=14.0, step=0.5,
            help="System losses excluding row shading: temperature, wiring, inverter, soiling, etc."
        )
    with c7:
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
            results = run_all_configs(lat, lon, gcr_1p, gcr_2p, base_loss)
        except Exception as e:
            st.error(f"❌ PVGIS API error: {e}. Check coordinates or try again in a moment.")
            st.stop()

    increment_usage(_uid, "yieldiq")

    best_sy = max(results[c]["spec_y"] for c in CONFIG_ORDER if c in results)

    # ── Section: Comparison Table ─────────────────────────────────────────────
    st.markdown('<div class="yiq-section">📊 Configuration Comparison</div>', unsafe_allow_html=True)

    # Column headers
    hdr_cols = st.columns([1.6, 0.7, 1.0, 1.0, 1.4, 1.4, 0.8, 0.8])
    for col, txt in zip(hdr_cols, [
        "Configuration","GCR","Shading Loss","Total Loss",
        "Specific Yield","Annual Energy","PR","CF"
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
        is_best = r["spec_y"] == best_sy
        best_badge = (' <span style="background:#e8f5e9;color:#2e7d32;font-size:0.62rem;'
                      'font-weight:700;padding:1px 7px;border-radius:10px;">BEST</span>'
                      if is_best else "")
        row_cols = st.columns([1.6, 0.7, 1.0, 1.0, 1.4, 1.4, 0.8, 0.8])
        row_cols[0].markdown(
            f'<div style="padding:6px 0;font-weight:700;font-size:0.95rem;">'
            f'{cfg}{best_badge}</div>', unsafe_allow_html=True)
        row_cols[1].markdown(
            f'<div style="padding:6px 0;color:#3a5a3a;">{r["gcr"]:.2f}</div>',
            unsafe_allow_html=True)
        row_cols[2].markdown(
            f'<div style="padding:6px 0;color:#d4840a;font-weight:600;">{r["shading"]:.1f}%</div>',
            unsafe_allow_html=True)
        row_cols[3].markdown(
            f'<div style="padding:6px 0;color:#5a7a5a;">{r["total_loss"]:.1f}%</div>',
            unsafe_allow_html=True)
        row_cols[4].markdown(
            f'<div style="padding:6px 0;font-weight:700;color:#1565c0;font-size:1.05rem;">'
            f'{r["spec_y"]:,.0f} kWh/kWp</div>', unsafe_allow_html=True)
        row_cols[5].markdown(
            f'<div style="padding:6px 0;font-weight:600;">'
            f'{r["spec_y"] * dc_kwp / 1000:,.1f} MWh/yr</div>', unsafe_allow_html=True)
        row_cols[6].markdown(
            f'<div style="padding:6px 0;">'
            f'{r["pr"]:.1f}%' if r["pr"] else '—</div>',
            unsafe_allow_html=True)
        row_cols[7].markdown(
            f'<div style="padding:6px 0;">{r["cf"]:.1f}%</div>',
            unsafe_allow_html=True)

    # ── Tracker gain ──────────────────────────────────────────────────────────
    gain_cols = st.columns(2)
    for i, pref in enumerate(["1P", "2P"]):
        fix, trk = f"{pref} Fixed", f"{pref} Tracker"
        if fix in results and trk in results:
            g    = results[trk]["spec_y"] - results[fix]["spec_y"]
            gpct = g / results[fix]["spec_y"] * 100
            gain_cols[i].metric(
                f"Tracker Gain ({pref})",
                f"+{g:,.0f} kWh/kWp/yr",
                f"+{gpct:.1f}% vs Fixed"
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
    chart_bytes = make_monthly_chart(results, dc_kwp)
    st.image(chart_bytes, use_container_width=True)

    # ── PDF download (generated once, shown immediately) ──────────────────────
    st.markdown("---")
    pdf_bytes = build_pdf(
        project_name, lat, lon, dc_kwp, gcr_1p, gcr_2p, base_loss,
        results, chart_bytes, best_sy
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
