"""
pvmath_yield.py — Single source of truth for PVGIS yield across SiteIQ / YieldIQ.

Two explicit profiles (Option B):
  screening  — SiteIQ quick go/no-go: flat 14% loss, no row-shading
  analysis   — YieldIQ pre-layout: disclosed soiling + other + GCR shading
"""

from __future__ import annotations

import concurrent.futures
from typing import Optional

import requests

from pvmath_capacity import GCR_SCREEN_LO

PVGIS_URL = "https://re.jrc.ec.europa.eu/api/v5_2/PVcalc"
USER_AGENT = "PVMath/1.0 (pvmath.com; contact@pvmath.com)"

PROFILE_SCREENING = "screening"
PROFILE_ANALYSIS = "analysis"

SCREENING_LOSS_PCT = 14.0
DEFAULT_SOILING_PCT = 2.0
DEFAULT_OTHER_LOSS_PCT = 6.0
DEFAULT_GCR_1P = GCR_SCREEN_LO

MOUNT_FIXED = "Fixed Tilt"
MOUNT_TRACKER = "Single-Axis Tracker"

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

CONFIG_ORDER = ["1P Fixed", "2P Fixed", "1P Tracker", "2P Tracker"]

_GCR_TABLE = [
    (0.20, 0.3), (0.25, 0.5), (0.30, 1.0), (0.35, 2.0),
    (0.40, 3.5), (0.45, 5.5), (0.50, 8.0), (0.60, 12.0),
]


def mount_is_tracker(mount_type: str) -> bool:
    return mount_type == MOUNT_TRACKER


def config_to_mount_tracker(config_name: str) -> tuple[bool, bool]:
    """Return (tracker, two_portrait) for a YieldIQ config label."""
    return "Tracker" in config_name, config_name.startswith("2P")


def gcr_shading(gcr: float, tracker: bool) -> float:
    """Row shading loss (%) from GCR. Tracker backtracking ≈ 40% of fixed shading."""
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


def loss_input_pct(
    profile: str,
    *,
    gcr: float = DEFAULT_GCR_1P,
    tracker: bool = False,
    soiling: float = DEFAULT_SOILING_PCT,
    other: float = DEFAULT_OTHER_LOSS_PCT,
) -> tuple[float, float]:
    """Return (pvgis_loss_input_pct, shading_pct) for the profile."""
    if profile == PROFILE_SCREENING:
        return SCREENING_LOSS_PCT, 0.0
    shade = gcr_shading(gcr, tracker)
    return min(soiling + other + shade, 30.0), shade


def _safe_float(v) -> Optional[float]:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def call_pvgis(
    lat: float,
    lon: float,
    total_loss_pct: float,
    tracker: bool,
    raddatabase: str | None = None,
) -> dict:
    """One PVGIS PVcalc call (peakpower=1 kWp → specific yield)."""
    params = {
        "lat": round(lat, 5),
        "lon": round(lon, 5),
        "peakpower": 1,
        "loss": round(total_loss_pct, 1),
        "pvtechchoice": "crystSi",
        "mountingplace": "free",
        "outputformat": "json",
        "browser": 0,
    }
    if tracker:
        params["fixed"] = 0
        params["inclined_axis"] = 1
        params["inclinedaxisangle"] = 0
    else:
        params["fixed"] = 1
        params["optimalinclination"] = 1
        params["optimalangles"] = 1
    if raddatabase:
        params["raddatabase"] = raddatabase

    resp = requests.get(
        PVGIS_URL, params=params, timeout=30,
        headers={"User-Agent": USER_AGENT},
    )
    resp.raise_for_status()
    data = resp.json()

    out = data["outputs"]
    totals_d = out.get("totals", {})
    monthly_d = out.get("monthly", {})
    radiation_db = data.get("inputs", {}).get("meteo_data", {}).get("radiation_db")

    if tracker:
        key = "inclined_axis" if "inclined_axis" in totals_d else next(iter(totals_d), None)
    else:
        key = "fixed" if "fixed" in totals_d else next(iter(totals_d), None)
    if not key:
        raise ValueError("Unexpected PVGIS response structure")

    tot = totals_d[key]
    monthly_raw = monthly_d.get(key, [])

    spec_y = float(tot.get("E_y", 0))
    h_y = float(tot.get("H(i)_y", 0))
    monthly = [float(m.get("E_m", 0)) for m in monthly_raw]

    pr = round(spec_y / h_y * 100, 1) if h_y else None
    cf = round(spec_y / 8760 * 100, 1)

    l_aoi = _safe_float(tot.get("l_aoi"))
    l_spec = _safe_float(tot.get("l_spec"))
    l_tg = _safe_float(tot.get("l_tg"))
    l_total = _safe_float(tot.get("l_total"))

    opt_tilt = None
    if not tracker:
        fixed_ms = data.get("inputs", {}).get("mounting_system", {}).get("fixed", {})
        slope = fixed_ms.get("slope", {})
        if isinstance(slope, dict):
            v = slope.get("value")
            opt_tilt = float(v) if v is not None else None
        elif isinstance(slope, (int, float)):
            opt_tilt = float(slope)

    monthly_chart = [
        {"Month": MONTHS[i], "GHI (kWh/m²)": round(m.get("H(i)_m", 0), 1)}
        for i, m in enumerate(monthly_raw[:12])
    ]

    return {
        "spec_y": round(spec_y, 0),
        "annual_yield": round(spec_y, 1),
        "annual_ghi": round(h_y, 1),
        "h_y": round(h_y, 1),
        "monthly": [round(x, 1) for x in monthly],
        "monthly_chart": monthly_chart,
        "pr": pr,
        "cf": cf,
        "opt_tilt": opt_tilt,
        "optimal_tilt": opt_tilt,
        "radiation_db": radiation_db,
        "l_aoi": round(l_aoi, 1) if l_aoi is not None else None,
        "l_spec": round(l_spec, 1) if l_spec is not None else None,
        "l_tg": round(l_tg, 1) if l_tg is not None else None,
        "l_total": round(l_total, 1) if l_total is not None else None,
        "tracker": tracker,
        "profile": None,
    }


def format_pvgis_total_loss(res: dict) -> str:
    """PVGIS combined loss (l_total) — temperature + AOI + spectral + user input."""
    val = res.get("l_total")
    if val is None:
        val = res.get("total_loss", 0)
    return f"{val:.1f}%"


def resolve_raddatabase(lat: float, lon: float, profile: str = PROFILE_ANALYSIS,
                        soiling: float = DEFAULT_SOILING_PCT,
                        other: float = DEFAULT_OTHER_LOSS_PCT) -> str | None:
    """Pin one radiation DB per site (ERA5 fallback on failure)."""
    loss, _ = loss_input_pct(profile, soiling=soiling, other=other)
    try:
        probe = call_pvgis(lat, lon, loss, False)
        return probe.get("radiation_db")
    except Exception:
        try:
            probe = call_pvgis(lat, lon, loss, False, raddatabase="PVGIS-ERA5")
            return probe.get("radiation_db") or "PVGIS-ERA5"
        except Exception:
            return None


def fetch_yield(
    lat: float,
    lon: float,
    mount_type: str,
    profile: str,
    *,
    gcr: float = DEFAULT_GCR_1P,
    soiling: float = DEFAULT_SOILING_PCT,
    other: float = DEFAULT_OTHER_LOSS_PCT,
    raddatabase: str | None = None,
) -> dict:
    """Fetch yield for one mount type and profile. Adds profile metadata."""
    tracker = mount_is_tracker(mount_type)
    loss, shade = loss_input_pct(
        profile, gcr=gcr, tracker=tracker, soiling=soiling, other=other,
    )
    res = call_pvgis(lat, lon, loss, tracker, raddatabase=raddatabase)
    res["profile"] = profile
    res["mount_type"] = mount_type
    res["gcr"] = gcr if profile == PROFILE_ANALYSIS else None
    res["shading"] = shade
    res["soiling_loss"] = soiling if profile == PROFILE_ANALYSIS else None
    res["other_loss"] = other if profile == PROFILE_ANALYSIS else None
    res["total_loss"] = round(loss, 1)
    res["success"] = True
    return res


def fetch_yield_with_fallback(
    lat: float,
    lon: float,
    mount_type: str,
    profile: str,
    **kwargs,
) -> dict:
    """fetch_yield with PVGIS-ERA5 fallback (SiteIQ global coverage)."""
    try:
        return fetch_yield(lat, lon, mount_type, profile, **kwargs)
    except Exception as e1:
        try:
            return fetch_yield(
                lat, lon, mount_type, profile,
                raddatabase="PVGIS-ERA5", **kwargs,
            )
        except Exception as e2:
            return {"success": False, "error": f"{e1} / ERA5 fallback: {e2}"}


def get_solar_data(lat: float, lon: float, mount_type: str = MOUNT_FIXED) -> dict:
    """SiteIQ entry — screening profile with ERA5 fallback."""
    res = fetch_yield_with_fallback(lat, lon, mount_type, PROFILE_SCREENING)
    if res.get("success"):
        res["monthly"] = res.get("monthly_chart", [])
    return res


def fetch_screening_yields(
    lat: float,
    lon: float,
    raddatabase: str | None = None,
) -> dict[str, float]:
    """SiteIQ screening reference yields for YieldIQ cross-reference (1P only)."""
    out: dict[str, float] = {}

    def _one(cfg: str, tracker: bool):
        loss, _ = loss_input_pct(PROFILE_SCREENING)
        res = call_pvgis(lat, lon, loss, tracker, raddatabase=raddatabase)
        out[cfg] = res["spec_y"]

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
        futs = [
            ex.submit(_one, "1P Fixed", False),
            ex.submit(_one, "1P Tracker", True),
        ]
        for f in futs:
            f.result()
    return out


def fetch_analysis_reference(
    lat: float,
    lon: float,
    mount_type: str,
    raddatabase: str | None = None,
    gcr: float = DEFAULT_GCR_1P,
    soiling: float = DEFAULT_SOILING_PCT,
    other: float = DEFAULT_OTHER_LOSS_PCT,
) -> dict | None:
    """YieldIQ analysis reference at defaults — for SiteIQ cross-reference."""
    try:
        return fetch_yield(
            lat, lon, mount_type, PROFILE_ANALYSIS,
            gcr=gcr, soiling=soiling, other=other, raddatabase=raddatabase,
        )
    except Exception:
        try:
            return fetch_yield(
                lat, lon, mount_type, PROFILE_ANALYSIS,
                gcr=gcr, soiling=soiling, other=other, raddatabase="PVGIS-ERA5",
            )
        except Exception:
            return None


def run_all_configs(
    lat: float,
    lon: float,
    gcr_1p: float,
    gcr_2p: float,
    soiling_loss: float,
    other_loss: float,
):
    """YieldIQ — four analysis-profile PVGIS calls, one shared radiation DB."""
    base_loss = soiling_loss + other_loss
    cfg_params = {
        "1P Fixed": (gcr_1p, False),
        "2P Fixed": (gcr_2p, False),
        "1P Tracker": (gcr_1p, True),
        "2P Tracker": (gcr_2p, True),
    }

    raddatabase = resolve_raddatabase(
        lat, lon, PROFILE_ANALYSIS, soiling=soiling_loss, other=other_loss,
    )

    def _call(name, gcr, tracker):
        shade = gcr_shading(gcr, tracker)
        total_loss = min(base_loss + shade, 30.0)
        try:
            res = call_pvgis(lat, lon, total_loss, tracker, raddatabase=raddatabase)
        except Exception:
            res = call_pvgis(lat, lon, total_loss, tracker)
        res["gcr"] = gcr
        res["shading"] = shade
        res["total_loss"] = round(total_loss, 1)
        res["tracker"] = tracker
        res["soiling_loss"] = soiling_loss
        res["other_loss"] = other_loss
        res["profile"] = PROFILE_ANALYSIS
        return name, res

    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
        futs = {ex.submit(_call, n, g, t): n for n, (g, t) in cfg_params.items()}
        for fut in concurrent.futures.as_completed(futs):
            name, res = fut.result()
            results[name] = res
    return results, raddatabase


# ── Cross-module disclosure (same release — not optional footnote-only) ────────

def profile_description(profile: str) -> str:
    if profile == PROFILE_SCREENING:
        return (
            f"SiteIQ screening profile — flat {SCREENING_LOSS_PCT:.0f}% PVGIS system-loss input, "
            "no row-shading (conservative quick go/no-go, like PVWatts-simple)"
        )
    return (
        f"YieldIQ analysis profile — {DEFAULT_SOILING_PCT:.0f}% soiling + "
        f"{DEFAULT_OTHER_LOSS_PCT:.0f}% other + GCR-based row shading at your selected GCR, "
        "plus PVGIS temperature/AOI/spectral derates (like PVsyst-detailed)"
    )


def yield_cross_ref_siteiq_html(
    screening_spec_y: float,
    analysis: dict,
    mount_type: str,
) -> str:
    """SiteIQ results page — show YieldIQ analysis reference alongside screening yield."""
    a_y = analysis.get("spec_y") or analysis.get("annual_yield")
    gcr = analysis.get("gcr", DEFAULT_GCR_1P)
    delta = a_y - screening_spec_y
    pct = (delta / screening_spec_y * 100) if screening_spec_y else 0
    sign = "+" if delta >= 0 else ""
    cfg = "1P Tracker" if mount_is_tracker(mount_type) else "1P Fixed"
    return (
        f'<div style="font-size:0.88rem;color:#1a3a1a;background:#eef6ff;'
        f'border:1px solid #b8d4f0;border-left:4px solid #1565c0;border-radius:8px;'
        f'padding:0.65rem 0.9rem;margin:0.75rem 0;">'
        f'<strong>Cross-module yield reference</strong> — two profiles, one site, both intentional:<br>'
        f'<span style="color:#2e5a2e;">● <b>SiteIQ screening</b> ({mount_type}): '
        f'<b>{screening_spec_y:,.0f} kWh/kWp/yr</b> — {profile_description(PROFILE_SCREENING)}.</span><br>'
        f'<span style="color:#1a4a7a;">● <b>YieldIQ analysis</b> ({cfg} @ GCR {gcr:.2f}): '
        f'<b>{a_y:,.0f} kWh/kWp/yr</b> ({sign}{delta:,.0f} / {sign}{pct:.1f}%) — '
        f'{profile_description(PROFILE_ANALYSIS)}.</span><br>'
        f'<span style="color:#5a6a5a;font-size:0.82rem;">'
        f'A gap here is expected, not a bug — run YieldIQ for full configuration comparison.</span>'
        f'</div>'
    )


def yield_cross_ref_yieldiq_html(
    screening: dict[str, float],
    results: dict,
    gcr_1p: float,
    soiling: float,
    other: float,
) -> str:
    """YieldIQ results page — show SiteIQ screening baseline alongside analysis runs."""
    lines = []
    for cfg in ("1P Fixed", "1P Tracker"):
        if cfg not in results or cfg not in screening:
            continue
        s_y = screening[cfg]
        a_y = results[cfg]["spec_y"]
        delta = a_y - s_y
        pct = (delta / s_y * 100) if s_y else 0
        sign = "+" if delta >= 0 else ""
        gcr = results[cfg]["gcr"]
        lines.append(
            f'<b>{cfg}</b>: SiteIQ screening <b>{s_y:,.0f}</b> kWh/kWp/yr → '
            f'this run (analysis @ GCR {gcr:.2f}) <b>{a_y:,.0f}</b> '
            f'({sign}{delta:,.0f} / {sign}{pct:.1f}%)'
        )
    body = "<br>".join(lines)
    return (
        f'<div style="font-size:0.88rem;color:#1a3a1a;background:#f5f8f5;'
        f'border:1px solid #c8dcc8;border-left:4px solid #1d9e52;border-radius:8px;'
        f'padding:0.65rem 0.9rem;margin:0.75rem 0;">'
        f'<strong>Cross-module yield reference</strong> — SiteIQ screening vs this YieldIQ analysis run:<br>'
        f'{body}<br>'
        f'<span style="color:#5a6a5a;font-size:0.82rem;">'
        f'SiteIQ uses {SCREENING_LOSS_PCT:.0f}% flat loss (no row-shading). '
        f'This run uses {soiling:.1f}% soiling + {other:.1f}% other + GCR shading at '
        f'GCR {gcr_1p:.2f} (1P) — plus PVGIS temperature/AOI/spectral. '
        f'Differences are methodology, not an error.</span>'
        f'</div>'
    )


def yield_cross_ref_pdf_text(
    screening_spec_y: float,
    analysis_spec_y: float | None,
    mount_type: str,
    gcr: float = DEFAULT_GCR_1P,
) -> str:
    """One paragraph for SiteIQ or YieldIQ PDF."""
    cfg = "1P Tracker" if mount_is_tracker(mount_type) else "1P Fixed"
    base = (
        f"Cross-module yield: SiteIQ screening ({mount_type}) = {screening_spec_y:,.0f} kWh/kWp/yr "
        f"({SCREENING_LOSS_PCT:.0f}% flat loss, no row-shading). "
    )
    if analysis_spec_y is not None:
        delta = analysis_spec_y - screening_spec_y
        sign = "+" if delta >= 0 else ""
        base += (
            f"YieldIQ analysis ({cfg} @ GCR {gcr:.2f}) = {analysis_spec_y:,.0f} kWh/kWp/yr "
            f"({sign}{delta:,.0f} kWh/kWp/yr). "
        )
    base += "Different profiles by design — screening vs pre-layout analysis."
    return base


def yield_cross_ref_yieldiq_pdf_text(
    screening: dict[str, float],
    results: dict,
) -> str:
    parts = []
    for cfg in ("1P Fixed", "1P Tracker"):
        if cfg not in screening or cfg not in results:
            continue
        s_y, a_y = screening[cfg], results[cfg]["spec_y"]
        gcr = results[cfg]["gcr"]
        delta = a_y - s_y
        sign = "+" if delta >= 0 else ""
        parts.append(
            f"{cfg}: SiteIQ screening {s_y:,.0f} → analysis @ GCR {gcr:.2f} {a_y:,.0f} "
            f"({sign}{delta:,.0f})"
        )
    return (
        "Cross-module yield reference — " + "; ".join(parts) + ". "
        f"SiteIQ screening = {SCREENING_LOSS_PCT:.0f}% flat loss, no row-shading. "
        "YieldIQ analysis = disclosed soiling/other + GCR shading + PVGIS physics derates."
    )
