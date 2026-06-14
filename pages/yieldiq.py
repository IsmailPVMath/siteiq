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

# ─────────────────────────────────────────────────────────────────────────────
# AUTH
# ─────────────────────────────────────────────────────────────────────────────
_uid = st.session_state.get("pvm_user_id", "guest")

# ─── Admin gate — YieldIQ is in development, not yet public ──────────────────
_ADMIN_EMAIL = "ismailpasha747@gmail.com"
if st.session_state.get("pvm_email", "") != _ADMIN_EMAIL:
    st.error("🔒 YieldIQ is coming soon. Stay tuned!")
    st.stop()

# ─────────────────────────────────────────────────────────────────────────────
# CSS
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("""
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap"
      rel="stylesheet">
<style>
html, body, [class*="css"] {
    font-family:'Inter','Segoe UI',system-ui,-apple-system,sans-serif !important;
    font-size:16px !important;
}
[data-testid="stMarkdown"] p,
[data-testid="stMarkdown"] li   { font-size:1rem !important; line-height:1.7 !important; }
[data-testid="stRadio"] label span { font-size:1rem !important; }
[data-testid="stSelectbox"] label,
[data-testid="stTextInput"] label,
[data-testid="stNumberInput"] label,
[data-testid="stSlider"] label  {
    font-size:0.97rem !important; font-weight:600 !important; color:#2a3820 !important;
}
[data-testid="stMetricValue"]   { font-size:1.55rem !important; font-weight:700 !important; }
[data-testid="stMetricLabel"]   { font-size:0.82rem !important; font-weight:500 !important; }
div[data-testid="stButton"] > button {
    border-radius:8px !important; font-weight:600 !important; font-size:0.97rem !important;
}
.yiq-section {
    font-size:1.05rem; font-weight:700; color:#d4840a;
    border-bottom:2px solid #fef3e2; padding-bottom:0.4rem;
    margin:1.4rem 0 0.9rem 0;
}
.yiq-row {
    display:flex; align-items:center; padding:0.45rem 0;
    border-bottom:1px solid #f0f4f0;
}
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
CHART_COLORS  = ["#1565c0", "#42a5f5", "#2e7d32", "#66bb6a"]


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
    ax.set_facecolor("#f8faf8")

    for i, (cfg, color) in enumerate(zip(CONFIG_ORDER, CHART_COLORS)):
        if cfg not in results:
            continue
        vals_mwh = [v * dc_kwp / 1000 for v in results[cfg]["monthly"]]
        offset   = (i - 1.5) * width
        ax.bar(x + offset, vals_mwh, width, label=cfg, color=color,
               alpha=0.88, edgecolor="white", linewidth=0.5)

    ax.set_xlabel("Month", fontsize=10, labelpad=5)
    ax.set_ylabel("Energy output (MWh)", fontsize=10, labelpad=5)
    ax.set_xticks(x)
    ax.set_xticklabels(MONTHS, fontsize=9)
    ax.tick_params(axis="y", labelsize=9)
    ax.legend(framealpha=0.85, fontsize=9, loc="upper left", ncol=2)
    ax.grid(axis="y", alpha=0.3, linewidth=0.5)
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_title(
        f"Monthly Energy Output — {dc_kwp:,.0f} kWp System",
        fontsize=11, fontweight="bold", pad=10
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
    lbl  = S("lbl",  fontSize=7.5, fontName="Helvetica-Bold",
             textColor=colors.HexColor("#6a8a6a"))
    bod  = S("bod",  fontSize=9,   textColor=colors.HexColor("#2a3a2a"), leading=13)
    sh   = S("sh",   fontSize=11,  fontName="Helvetica-Bold",
             textColor=colors.HexColor("#145f34"), spaceAfter=5)
    note = S("note", fontSize=7.5, textColor=colors.HexColor("#8a9a8a"), leading=11)
    def lp(txt, style=bod): return Paragraph(str(txt), style)

    story = []

    # ── Green header bar ──────────────────────────────────────────────────────
    hdr = Table([[
        lp("YieldIQ ⚡", S("ht", fontSize=15, fontName="Helvetica-Bold",
                            textColor=colors.white)),
        lp("PVMath · Solar Site Intelligence · pvmath.com",
           S("hs", fontSize=8.5, textColor=colors.HexColor("#c8e6c9"),
             alignment=TA_RIGHT)),
    ]], colWidths=["55%","45%"])
    hdr.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,-1), colors.HexColor("#145f34")),
        ("VALIGN",        (0,0),(-1,-1), "MIDDLE"),
        ("TOPPADDING",    (0,0),(-1,-1), 10),
        ("BOTTOMPADDING", (0,0),(-1,-1), 10),
        ("LEFTPADDING",   (0,0),(-1,-1), 12),
        ("RIGHTPADDING",  (0,0),(-1,-1), 12),
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
        ("BACKGROUND",    (0,0),(-1,-1), colors.HexColor("#f5f9f5")),
        ("BOX",           (0,0),(-1,-1), 0.5, colors.HexColor("#c8e0c8")),
        ("TOPPADDING",    (0,0),(-1,-1), 5),
        ("BOTTOMPADDING", (0,0),(-1,-1), 5),
        ("LEFTPADDING",   (0,0),(-1,-1), 8),
    ]))
    story += [info, Spacer(1, 0.5*cm)]

    # ── Results table ─────────────────────────────────────────────────────────
    story.append(lp("Configuration Comparison", sh))
    hdr_row = [lp(h, lbl) for h in [
        "Configuration","GCR","Shading\nLoss","Total\nLoss",
        "Specific Yield\n(kWh/kWp/yr)","Annual Energy\n(MWh/yr)","PR (%)","CF (%)"
    ]]
    rows = [hdr_row]
    for cfg in CONFIG_ORDER:
        if cfg not in results:
            continue
        r  = results[cfg]
        is_best = r["spec_y"] == best_sy
        sy_style = S("sy", fontSize=10, fontName="Helvetica-Bold",
                     textColor=colors.HexColor("#1565c0"))
        rows.append([
            lp(cfg + (" ★" if is_best else ""),
               S("cf", fontSize=9,
                 fontName="Helvetica-Bold" if is_best else "Helvetica",
                 textColor=colors.HexColor("#1a2e1a"))),
            lp(f"{r['gcr']:.2f}", bod),
            lp(f"{r['shading']:.1f}%", bod),
            lp(f"{r['total_loss']:.1f}%", bod),
            lp(f"{r['spec_y']:,.0f}", sy_style),
            lp(f"{r['spec_y'] * dc_kwp / 1000:,.1f}", bod),
            lp(f"{r['pr']:.1f}%" if r["pr"] else "—", bod),
            lp(f"{r['cf']:.1f}%", bod),
        ])
    res_tbl = Table(rows, colWidths=["3cm","1.4cm","1.7cm","1.7cm","3cm","2.8cm","1.5cm","1.5cm"])
    res_tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1, 0), colors.HexColor("#e8f5e9")),
        ("BOX",           (0,0),(-1,-1), 0.5, colors.HexColor("#c8e0c8")),
        ("INNERGRID",     (0,0),(-1,-1), 0.3, colors.HexColor("#ddeedd")),
        ("VALIGN",        (0,0),(-1,-1), "MIDDLE"),
        ("TOPPADDING",    (0,0),(-1,-1), 5),
        ("BOTTOMPADDING", (0,0),(-1,-1), 5),
        ("LEFTPADDING",   (0,0),(-1,-1), 5),
        ("ROWBACKGROUNDS",(0,1),(-1,-1), [colors.white, colors.HexColor("#f5f9f5")]),
    ]))
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
    story.append(lp("Monthly Energy Profile", sh))
    story.append(RLImage(io.BytesIO(chart_bytes), width=16*cm, height=6.5*cm))
    story += [Spacer(1, 0.5*cm),
              HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#c8e0c8")),
              Spacer(1, 0.3*cm)]

    # ── Disclaimer ────────────────────────────────────────────────────────────
    story.append(lp(
        "DISCLAIMER: Preliminary yield estimates for pre-feasibility use only. Results are based on "
        "PVGIS (EC JRC) irradiance data and simplified row shading models derived from GCR. "
        "PVMath does not claim bankability. A certified energy yield assessment (PVsyst or equivalent) "
        "is required for financing, permitting, and EPC decisions.", note))
    story.append(Spacer(1, 0.15*cm))
    story.append(lp(
        "Generated by YieldIQ — PVMath Solar Site Intelligence Platform | pvmath.com | "
        "Data: PVGIS (EC JRC). For professional use only.", note))

    doc.build(story)
    buf.seek(0)
    return buf.read()


# ─────────────────────────────────────────────────────────────────────────────
# INPUT FORM
# ─────────────────────────────────────────────────────────────────────────────
st.markdown('<div class="yiq-section">📍 Project Inputs</div>', unsafe_allow_html=True)

with st.form("yieldiq_form"):
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
            "DC Capacity (kWp)", min_value=1.0, max_value=1_000_000.0,
            value=10_000.0, step=500.0,
            help="Total rated DC power of the system."
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
    lat, lon = parse_location(location_raw)
    if lat is None:
        st.error("❌ Could not parse location. Paste coordinates as '48.137, 11.576' or a Google Maps URL.")
        st.stop()
    if not -90 <= lat <= 90 or not -180 <= lon <= 180:
        st.error("❌ Coordinates out of range. Check lat/lon order.")
        st.stop()
    if not project_name.strip():
        project_name = f"YieldIQ Site {lat:.3f}°, {lon:.3f}°"

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
