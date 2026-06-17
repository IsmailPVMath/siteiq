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
    remaining, FREE_LIMIT, STRIPE_LINK,
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
        f"[Upgrade to Professional]({STRIPE_LINK})"
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


def call_pvgis(lat: float, lon: float, total_loss_pct: float, tracker: bool,
               raddatabase: str = None) -> dict:
    """
    Call PVGIS PVcalc with peakpower=1 kWp.
    Returns specific yield (kWh/kWp/yr), monthly values, PR, CF, optimal tilt.

    raddatabase: pin an explicit radiation database (e.g. "PVGIS-ERA5"). If
    left None, PVGIS auto-selects one (PVGIS-SARAH2 where it has coverage).
    Auto-selection is resolved ONCE per site by run_all_configs() and then
    passed in explicitly here for every config — see note there on why.
    """
    params = {
        "lat": round(lat, 5), "lon": round(lon, 5),
        "peakpower": 1,                    # always 1 → results = specific yield
        "loss": round(total_loss_pct, 1),
        "pvtechchoice": "crystSi",
        "mountingplace": "free",
        "outputformat": "json",
        "browser": 0,
    }
    # IMPORTANT: PVGIS's PVcalc tool (this endpoint) has NO "trackingtype"
    # parameter — that field only exists on PVGIS's separate hourly/seriescalc
    # endpoint. PVcalc's own tracking controls are different flags entirely
    # (confirmed against PVGIS's official "API non-interactive service" docs):
    #   fixed=1 (default)         → flat-tilt fixed system
    #   inclined_axis=1 + inclinedaxisangle=0  → single horizontal-axis N-S
    #                                             tracker (= standard SAT)
    #   vertical_axis / twoaxis   → other tracking types, unused here
    # The old code sent "trackingtype": 1 for trackers, which PVcalc silently
    # ignores (unrecognized param) — it then fell back to its own default
    # fixed=1, angle=0° (since optimalinclination/optimalangles were only set
    # on the non-tracker branch), i.e. every "tracker" call was actually
    # returning a flat, non-optimized FIXED-tilt result. That's the real
    # cause of trackers consistently showing lower yield than fixed tilt.
    if tracker:
        params["fixed"]            = 0   # disable PVGIS's default fixed calc
        params["inclined_axis"]    = 1
        params["inclinedaxisangle"] = 0  # axis itself is horizontal (true SAT)
    else:
        params["fixed"]            = 1
        params["optimalinclination"] = 1
        params["optimalangles"]      = 1
    if raddatabase:
        params["raddatabase"] = raddatabase

    resp = requests.get(
        PVGIS_URL, params=params, timeout=30,
        headers={"User-Agent": "YieldIQ/1.0 (pvmath.com; contact@pvmath.com)"}
    )
    resp.raise_for_status()
    data = resp.json()

    out        = data["outputs"]
    totals_d   = out.get("totals",  {})
    monthly_d  = out.get("monthly", {})
    radiation_db = data.get("inputs", {}).get("meteo_data", {}).get("radiation_db")

    # PVcalc nests results under a key matching whichever system type was
    # actually requested: "fixed" for fixed=1, "inclined_axis" for the
    # single-axis tracker config requested above. With fixed=0 explicitly set
    # for trackers, "fixed" should no longer appear in the response at all —
    # but we still check the tracker-specific key FIRST as a safety net,
    # since blindly preferring "fixed" (the old behavior) is exactly what
    # caused tracker calls to silently read back fixed-tilt results before.
    if tracker:
        key = "inclined_axis" if "inclined_axis" in totals_d else next(iter(totals_d), None)
    else:
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

    # PVGIS computes its OWN physics-based loss components on top of the
    # "loss" % we send in (which only covers what we tell it — wiring,
    # inverter, soiling, mismatch, row shading). These three are added
    # automatically by the model based on technology/location/mounting:
    #   l_aoi   — angle-of-incidence reflection loss (%)
    #   l_spec  — spectral mismatch loss (%) — can be "not calculated" for
    #             some technologies, hence the float() guard below
    #   l_tg    — temperature & low-irradiance loss (%) — this is the real,
    #             physics-derived "Temperature" loss line item, not a guess
    #   l_total — true total loss (%), i.e. our input loss + l_aoi + l_spec
    #             + l_tg combined. More accurate than self-tracking total_loss
    #             since it includes effects PVGIS models that we don't.
    def _safe_float(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    l_aoi   = _safe_float(tot.get("l_aoi"))
    l_spec  = _safe_float(tot.get("l_spec"))
    l_tg    = _safe_float(tot.get("l_tg"))
    l_total = _safe_float(tot.get("l_total"))

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
        "radiation_db": radiation_db,
        "l_aoi":    round(l_aoi, 1) if l_aoi is not None else None,
        "l_spec":   round(l_spec, 1) if l_spec is not None else None,
        "l_tg":     round(l_tg, 1) if l_tg is not None else None,
        "l_total":  round(l_total, 1) if l_total is not None else None,
    }


def run_all_configs(lat, lon, gcr_1p, gcr_2p, soiling_loss, other_loss):
    """Run 4 PVGIS calls concurrently. Returns dict keyed by config name.

    soiling_loss + other_loss together form the same combined "system loss %"
    that used to be a single base_loss input — split in two now so Soiling
    can be shown as its own line item (PVGIS has no native soiling output,
    so this is the only honest way to surface it: as a user-specified input,
    not a number we invent).
    """
    base_loss = soiling_loss + other_loss
    cfg_params = {
        "1P Fixed":   (gcr_1p, False),
        "2P Fixed":   (gcr_2p, False),
        "1P Tracker": (gcr_1p, True),
        "2P Tracker": (gcr_2p, True),
    }

    # Resolve ONE radiation database for this site and reuse it for all 4
    # configs below. Left unpinned, PVGIS auto-selects per-call (PVGIS-SARAH2
    # where it has coverage, otherwise it errors/falls back on its own) — and
    # that auto-selection is not guaranteed to land on the same database for
    # fixed=1 (Fixed) vs inclined_axis=1 (Tracker) calls at the same
    # coordinates. Comparing Fixed vs Tracker yield is only meaningful if
    # both numbers came from the same underlying radiation data, so we probe
    # once, fall back to PVGIS-ERA5 (true global coverage) on failure exactly
    # like siteiq.py's get_solar_data() already does, and pin that result for
    # every config in this run.
    raddatabase = None
    try:
        probe = call_pvgis(lat, lon, base_loss, False)
        raddatabase = probe.get("radiation_db")
    except Exception:
        try:
            probe = call_pvgis(lat, lon, base_loss, False, raddatabase="PVGIS-ERA5")
            raddatabase = probe.get("radiation_db") or "PVGIS-ERA5"
        except Exception:
            raddatabase = None  # let each call auto-select as a last resort

    def _call(name, gcr, tracker):
        shade      = gcr_shading(gcr, tracker)
        total_loss = min(base_loss + shade, 30.0)
        try:
            res = call_pvgis(lat, lon, total_loss, tracker, raddatabase=raddatabase)
        except Exception:
            # Pinned database rejected this call (rare) — fall back to letting
            # PVGIS auto-select rather than losing the config entirely.
            res = call_pvgis(lat, lon, total_loss, tracker)
        res["gcr"]          = gcr
        res["shading"]      = shade
        res["total_loss"]   = round(total_loss, 1)
        res["tracker"]      = tracker
        res["soiling_loss"] = soiling_loss
        res["other_loss"]   = other_loss
        return name, res

    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
        futs = {ex.submit(_call, n, g, t): n for n, (g, t) in cfg_params.items()}
        for fut in concurrent.futures.as_completed(futs):
            name, res = fut.result()
            results[name] = res
    return results, raddatabase


def get_ghi(lat, lon, raddatabase=None) -> float | None:
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


def get_dni_dhi(lat, lon, raddatabase=None) -> tuple:
    """Best-effort annual DNI/DHI (kWh/m²/yr) via PVGIS's MRcalc endpoint.

    UNVERIFIED: this sandbox cannot reach PVGIS's live API, so the exact
    JSON field names below are inferred from PVGIS's published parameter
    docs (input params "mr_dni", "horirrad", "d2g"), not confirmed against
    a real response. Parsing is intentionally defensive — any KeyError/
    shape mismatch returns (None, None) rather than a silently-wrong number.
    Treat these two values as experimental until checked against a live
    PVGIS call.
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
        data = resp.json()
        monthly = data["outputs"].get("monthly", [])
        if not monthly:
            return None, None

        def _sum_key(candidates):
            total = 0.0
            found = False
            for row in monthly:
                for k in candidates:
                    if k in row:
                        total += float(row[k])
                        found = True
                        break
            return round(total, 1) if found else None

        ghi_h = _sum_key(["H(h)_m", "H(h)", "Hh_m"])
        dni   = _sum_key(["Hb(n)_m", "Hb(n)", "DNI_m", "Hbn_m"])
        d2g   = None
        # diffuse-to-global ratio is monthly; weight by that month's GHI
        if ghi_h:
            dhi_total, dhi_found = 0.0, False
            for row in monthly:
                ghi_m = None
                for k in ["H(h)_m", "H(h)", "Hh_m"]:
                    if k in row:
                        ghi_m = float(row[k]); break
                ratio_m = None
                for k in ["d2g", "Kd"]:
                    if k in row:
                        ratio_m = float(row[k]); break
                if ghi_m is not None and ratio_m is not None:
                    dhi_total += ghi_m * ratio_m
                    dhi_found = True
            d2g = round(dhi_total, 1) if dhi_found else None
        return dni, d2g
    except Exception:
        return None, None


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


def build_pdf(project_name, lat, lon, dc_kwp, gcr_1p, gcr_2p, soiling_loss, other_loss,
              results, chart_bytes, best_sy, ghi=None, dni=None, dhi=None) -> bytes:
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
        [lp("SOILING / OTHER LOSSES", lbl), lp(f"{soiling_loss:.1f}% / {other_loss:.1f}% (excl. row shading)", bod),
         lp("DATA SOURCE", lbl), lp("PVGIS JRC (EU Commission)", bod)],
    ], colWidths=[3*cm, 6*cm, 3*cm, 6*cm])
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

    # ── Losses Breakdown (best-performing config) ────────────────────────────
    best_cfg = next((c for c in CONFIG_ORDER if c in results and results[c]["spec_y"] == best_sy), None)
    if best_cfg:
        _b = results[best_cfg]
        story.append(section_hdr(f"LOSSES BREAKDOWN — {best_cfg} (BEST CONFIG)"))
        story.append(Spacer(1, 0.15*cm))
        loss_tbl = Table([
            [lp("Shading", lbl), lp("Temperature", lbl), lp("Soiling", lbl), lp("Total Loss", lbl)],
            [lp(f"{_b['shading']:.1f}%", bod),
             lp(f"{_b['l_tg']:.1f}%" if _b.get("l_tg") is not None else "—", bod),
             lp(f"{_b['soiling_loss']:.1f}%", bod),
             lp(f"{_b['l_total']:.1f}%" if _b.get("l_total") is not None else f"{_b['total_loss']:.1f}%", bod)],
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
        "Configuration","GCR","Shading\nLoss","Total\nLoss",
        "POA Irrad.\n(kWh/m²/yr)","Specific Yield\n(kWh/kWp/yr)","Annual Energy\n(MWh/yr)","PR (%)","CF (%)"
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
        # POA (plane-of-array / in-plane irradiance, PVGIS field H(i)_y) — shown
        # alongside specific yield so a tracker's higher yield can be traced
        # back to genuinely higher captured irradiance, not just lower losses.
        rows.append([
            lp(cfg + (" ★" if is_best else ""), cfg_style),
            lp(f"{r['gcr']:.2f}", bod),
            lp(f"{r['shading']:.1f}%", bod),
            lp(f"{r['total_loss']:.1f}%", bod),
            lp(f"{r['h_y']:,.0f}", bod),
            lp(f"{r['spec_y']:,.0f}", sy_style),
            lp(f"{r['spec_y'] * dc_kwp / 1000:,.1f}", bod),
            lp(f"{r['pr']:.1f}%" if r["pr"] else "—", bod),
            lp(f"{r['cf']:.1f}%", bod),
        ])
        _cfg_row_colors.append(
            colors.HexColor("#f0faf4") if is_tracker else colors.HexColor("#fff4ee")
        )
    res_tbl = Table(rows, colWidths=[2.6*cm, 1.3*cm, 1.5*cm, 1.5*cm, 1.7*cm, 2.6*cm, 2.4*cm, 1.3*cm, 1.3*cm])
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
_has_proj  = _proj_lat is not None and _proj_lon is not None

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

# ── Capacity picker (shown when project area is known) ────────────────────────
# Previously this rendered all 4 land-use/mounting combinations side by side
# in one table. Laypeople read "highest MWp in the table" as "best system" —
# but capacity density and energy yield are different metrics, and the table
# invited exactly that mix-up. Now the user picks ONE combination up front and
# sees only that result, which removes the misleading comparison entirely.
_default_dc_kwp = 10_000.0
_scenario_label = "Custom"

if _has_proj and _proj_area:
    st.markdown('<div class="yiq-section">📐 Site Capacity for Your Area</div>',
                unsafe_allow_html=True)

    _pick_c1, _pick_c2 = st.columns(2)
    with _pick_c1:
        _pick_lu = st.radio("Land Use", ["Standard", "Agri-PV"],
                             key="yiq_pick_landuse", horizontal=True)
    with _pick_c2:
        _pick_mt = st.radio("Mounting", ["Fixed Tilt", "Single-Axis Tracker"],
                             key="yiq_pick_mount", horizontal=True)

    _pick_density = _DENSITY[(_pick_lu, _pick_mt)]
    _pick_mwp     = round(_proj_area * _pick_density, 1)
    _default_dc_kwp = _pick_mwp * 1000
    _scenario_label = f"{_pick_lu} · {_pick_mt}"

    st.markdown(f"""
    <div style="display:flex;align-items:center;gap:1.2rem;background:#f0faf5;
                border:1px solid #b8ddc8;border-radius:8px;padding:0.7rem 1rem;
                margin-bottom:0.7rem;">
      <div>
        <div style="font-size:0.7rem;font-weight:700;color:#5a7a5a;text-transform:uppercase;
                    letter-spacing:0.06em;">Density</div>
        <div style="font-size:1rem;font-weight:800;color:#145f34;">{_pick_density} MW/ha</div>
      </div>
      <div style="width:1px;height:32px;background:#b8ddc8;"></div>
      <div>
        <div style="font-size:0.7rem;font-weight:700;color:#5a7a5a;text-transform:uppercase;
                    letter-spacing:0.06em;">Est. Capacity for {_proj_area} ha</div>
        <div style="font-size:1.3rem;font-weight:800;color:#0d5c0d;">{_pick_mwp} MWp</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown(
        '<div style="font-size:0.82rem;color:#7a6a2a;background:#fff8e1;'
        'border-left:3px solid #d4840a;border-radius:6px;padding:0.55rem 0.8rem;'
        'margin:0 0 0.9rem 0;">'
        '⚠️ <strong>This is installable capacity (MWp), not energy performance.</strong> '
        'Fixed Tilt fits more MWp per hectare than Tracker because trackers need wider '
        'row spacing to avoid self-shading while rotating — lower density, not lower output. '
        'Trackers produce <strong>more energy per installed kWp</strong> (see Specific Yield, '
        'kWh/kWp/yr, in the results below after running the analysis).'
        '</div>', unsafe_allow_html=True
    )

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

    c3, c4, c5, c6, c7, c8 = st.columns(6)
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
        soiling_loss = st.number_input(
            "Soiling Loss (%)", min_value=0.0, max_value=10.0,
            value=2.0, step=0.5,
            help="Dust/dirt accumulation loss. Typical: 1–3% (temperate), 3–6% (arid/desert sites)."
        )
    with c7:
        other_loss = st.number_input(
            "Other System Losses (%)", min_value=3.0, max_value=20.0,
            value=12.0, step=0.5,
            help="Wiring, inverter, mismatch, availability — excludes row shading, soiling and "
                 "PVGIS's own temperature/AOI/spectral derates (those are computed automatically)."
        )
    with c8:
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
            results, raddatabase = run_all_configs(lat, lon, gcr_1p, gcr_2p, soiling_loss, other_loss)
        except Exception as e:
            st.error(f"❌ PVGIS API error: {e}. Check coordinates or try again in a moment.")
            st.stop()

    with st.spinner("Fetching solar resource data (GHI/DNI/DHI)…"):
        ghi        = get_ghi(lat, lon, raddatabase=raddatabase)
        dni, dhi   = get_dni_dhi(lat, lon, raddatabase=raddatabase)

    increment_usage(_uid, "yieldiq")

    best_sy  = max(results[c]["spec_y"] for c in CONFIG_ORDER if c in results)
    best_cfg = next(c for c in CONFIG_ORDER if c in results and results[c]["spec_y"] == best_sy)

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
        f'<div class="yiq-section">📉 Losses Breakdown — {best_cfg} (best config)</div>',
        unsafe_allow_html=True
    )
    _best = results[best_cfg]
    loss_cols = st.columns(4)
    loss_cols[0].metric("Shading", f"{_best['shading']:.1f}%")
    loss_cols[1].metric("Temperature", f"{_best['l_tg']:.1f}%" if _best.get("l_tg") is not None else "—")
    loss_cols[2].metric("Soiling", f"{_best['soiling_loss']:.1f}%")
    loss_cols[3].metric(
        "Total Loss",
        f"{_best['l_total']:.1f}%" if _best.get("l_total") is not None else f"{_best['total_loss']:.1f}%"
    )
    st.caption(
        "Temperature loss is PVGIS's own physics-based derate (not estimated). "
        "Total Loss is PVGIS's true combined figure (shading + soiling + other system losses + "
        "temperature + angle-of-incidence + spectral) where available."
    )

    # ── Section: Results — Configuration Comparison ───────────────────────────
    st.markdown('<div class="yiq-section">📊 Results — Configuration Comparison</div>', unsafe_allow_html=True)

    # Column headers
    _COL_W = [1.5, 0.7, 1.0, 1.0, 1.1, 1.4, 1.4, 0.8, 0.8]
    hdr_cols = st.columns(_COL_W)
    for col, txt in zip(hdr_cols, [
        "Configuration","GCR","Shading Loss","Total Loss",
        "POA Irrad.","Specific Yield","Annual Energy","PR","CF"
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
        row_cols = st.columns(_COL_W)
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
        # POA = plane-of-array / in-plane irradiance (PVGIS field H(i)_y).
        # Shown so a tracker's higher yield can be traced back to genuinely
        # higher captured irradiance, not just lower shading/loss.
        row_cols[4].markdown(
            f'<div style="padding:6px 0;color:#3a5a3a;">{r["h_y"]:,.0f} kWh/m²</div>',
            unsafe_allow_html=True)
        row_cols[5].markdown(
            f'<div style="padding:6px 0;font-weight:700;color:#1565c0;font-size:1.05rem;">'
            f'{r["spec_y"]:,.0f} kWh/kWp</div>', unsafe_allow_html=True)
        row_cols[6].markdown(
            f'<div style="padding:6px 0;font-weight:600;">'
            f'{r["spec_y"] * dc_kwp / 1000:,.1f} MWh/yr</div>', unsafe_allow_html=True)
        _pr_str = f'{r["pr"]:.1f}%' if r["pr"] else "—"
        row_cols[7].markdown(
            f'<div style="padding:6px 0;">{_pr_str}</div>',
            unsafe_allow_html=True)
        row_cols[8].markdown(
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
                f"{g:+,.0f} kWh/kWp/yr",
                f"{gpct:+.1f}% vs Fixed"
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
        project_name, lat, lon, dc_kwp, gcr_1p, gcr_2p, soiling_loss, other_loss,
        results, chart_bytes, best_sy, ghi, dni, dhi
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
