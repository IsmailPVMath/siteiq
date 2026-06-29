"""YieldIQ PDF section for the unified PVMath report.

Mirrors the React YieldResultsPanel exactly: same mount-type filtering,
Best/Selected logic, screening summary, solar resource, POA, losses
breakdown, configuration comparison, cross-module reference, tracker gain
and a single-config monthly specific-yield chart (solar-market blue).
"""

from __future__ import annotations

import io
from typing import Any, Dict, List, Optional

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import Image as RLImage, KeepTogether, Paragraph, Spacer, Table, TableStyle

from pvmath_reports.common import ACCENT, BORDER, DARK, LGRAY, MUTED, base_styles, lp, module_divider, section_hdr
from pvmath_yield import config_display_name

CONFIG_ORDER = ["1P Fixed", "2P Fixed", "1P Tracker", "2P Tracker"]
MONTHS_SHORT = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# Solar-market blue — distinct from SiteIQ's green irradiation chart.
YIELD_BLUE = "#1565c0"
YIELD_BLUE_DK = "#0d47a1"


def make_monthly_specific_yield_chart(monthly: List[float], title_cfg: str = "") -> bytes:
    """Single-config monthly specific yield (kWh/kWp), solar-market blue bars."""
    vals = [float(v or 0) for v in monthly[:12]]
    x = np.arange(len(vals))
    fig, ax = plt.subplots(figsize=(13, 4.6))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("#f4f7fb")

    ax.bar(x, vals, 0.66, color=YIELD_BLUE, alpha=0.92, edgecolor="white", linewidth=0.6)
    for xi, v in zip(x, vals):
        ax.text(xi, v + max(vals) * 0.015, f"{v:.0f}", ha="center", va="bottom",
                fontsize=7.5, color=YIELD_BLUE_DK, fontweight="bold")

    ax.set_xlabel("Month", fontsize=10, labelpad=5, color="#5a6b7a")
    ax.set_ylabel("Specific yield (kWh/kWp)", fontsize=10, labelpad=5, color="#5a6b7a")
    ax.set_xticks(x)
    ax.set_xticklabels(MONTHS_SHORT[:len(vals)], fontsize=9)
    ax.grid(axis="y", alpha=0.3, linewidth=0.5, color="#cfdcea")
    ax.spines[["top", "right"]].set_visible(False)
    if vals:
        ax.set_ylim(0, max(vals) * 1.15)
    ax.set_title(
        f"Monthly Specific Yield{(' — ' + title_cfg) if title_cfg else ''}",
        fontsize=11, fontweight="bold", pad=10, color="#13243a",
    )
    plt.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    return buf.getvalue()


def _matches_filter(key: str, mount_filter: str) -> bool:
    if mount_filter == "all":
        return True
    tracker = "Tracker" in key
    return tracker if mount_filter == "sat" else not tracker


def _fmt_loss(val: Any) -> str:
    if val is None or val == "":
        return "—"
    try:
        return f"{abs(float(val)):.1f}%"
    except (TypeError, ValueError):
        return "—"


def _fmt_num(val: Any, digits: int = 0) -> str:
    if val is None or val == "":
        return "—"
    try:
        return f"{float(val):,.{digits}f}"
    except (TypeError, ValueError):
        return "—"


def _disp_name(cfg: Dict[str, Any], key: str) -> str:
    return str(cfg.get("display_name") or config_display_name(key))


def _metrics_grid(pairs: List[tuple], st, cols: int = 3) -> Table:
    """A label/value metrics card grid like the app's yield-metrics-row."""
    cells = []
    for label, value in pairs:
        cells.append([lp(label, st["lbl"]), lp(value, st["body"])])
    inner = []
    for c in cells:
        t = Table([[c[0]], [c[1]]], colWidths=[(17.0 / cols) * cm])
        t.setStyle(TableStyle([
            ("TOPPADDING", (0, 0), (-1, -1), 1),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 0),
            ("BOTTOMPADDING", (0, 1), (-1, 1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ]))
        inner.append(t)
    rows = [inner[i:i + cols] for i in range(0, len(inner), cols)]
    if rows and len(rows[-1]) < cols:
        rows[-1] += [""] * (cols - len(rows[-1]))
    grid = Table(rows, colWidths=[(17.0 / cols) * cm] * cols)
    grid.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), LGRAY),
        ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.3, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]))
    return grid


def build_yieldiq_flowables(
    *,
    yield_result: Optional[Dict[str, Any]],
    mount_type: str = "Fixed Tilt",
    selected_config_key: Optional[str] = None,
    selected_dc_kwp: Optional[float] = None,
) -> List:
    st = base_styles()
    story: List = []

    story.extend(module_divider())
    story.append(section_hdr("YieldIQ — Energy yield", st))
    story.append(Spacer(1, 0.2 * cm))

    if not yield_result or not yield_result.get("configs"):
        story.append(lp("YieldIQ not run — select a layout row and run yield analysis.", st["muted"]))
        return story

    configs: Dict[str, Any] = yield_result["configs"]
    mount_filter = "sat" if "Tracker" in (mount_type or "") else "fixed"
    visible_keys = [k for k in CONFIG_ORDER if k in configs and _matches_filter(k, mount_filter)]
    if not visible_keys:
        visible_keys = [k for k in CONFIG_ORDER if k in configs]

    def _mwh(cfg: Dict[str, Any]) -> float:
        sy = float(cfg.get("spec_y") or 0)
        return (selected_dc_kwp * sy / 1000.0) if selected_dc_kwp else sy

    best_key = None
    for k in visible_keys:
        if best_key is None or _mwh(configs[k]) > _mwh(configs[best_key]):
            best_key = k
    best_cfg = configs.get(best_key) if best_key else None

    # Only honor an explicit selection that matches the active mount filter —
    # a stale Fixed-tilt layout row must not leak into a tracker report.
    sel_cfg = None
    if selected_config_key in configs and _matches_filter(selected_config_key, mount_filter):
        sel_cfg = configs[selected_config_key]
    else:
        selected_config_key = None
    screening_cfg = sel_cfg or best_cfg
    screening_key = selected_config_key if sel_cfg else best_key

    sel_mwh = (selected_dc_kwp * float(sel_cfg.get("spec_y") or 0) / 1000.0) if (selected_dc_kwp and sel_cfg) else None

    solar = yield_result.get("solar_resource") or {}
    cross = yield_result.get("cross_ref_bundle") or yield_result.get("cross_ref") or {}

    # --- Screening summary card ---
    if screening_cfg:
        monthly = [float(v or 0) for v in (screening_cfg.get("monthly") or [])]
        peak_i = monthly.index(max(monthly)) if monthly else -1
        low_i = monthly.index(min(monthly)) if monthly else -1
        soil_bos = (float(screening_cfg.get("soiling_loss") or 0) + float(screening_cfg.get("other_loss") or 0))
        pairs = [
            ("Configuration", _disp_name(screening_cfg, screening_key or "")),
            ("Specific yield", f"{float(screening_cfg.get('spec_y') or 0):.0f} kWh/kWp/yr"),
            ("Annual energy", f"{sel_mwh:.0f} MWh/yr" if sel_mwh is not None else "Select layout DC"),
            ("Performance ratio", f"{float(screening_cfg['pr']):.1f}%" if screening_cfg.get("pr") is not None else "—"),
            ("Capacity factor", f"{float(screening_cfg['cf']):.1f}%" if screening_cfg.get("cf") is not None else "—"),
            ("POA irradiance", f"{_fmt_num(screening_cfg.get('h_y'))} kWh/m²/yr"),
            ("Total loss", _fmt_loss(screening_cfg.get("l_total", screening_cfg.get("total_loss")))),
            ("Shading (GCR)", _fmt_loss(screening_cfg.get("shading"))),
            ("Temperature", _fmt_loss(screening_cfg.get("l_tg"))),
            ("Soiling + BOS", _fmt_loss(soil_bos)),
        ]
        if peak_i >= 0:
            pairs.append(("Peak month", f"{MONTHS_SHORT[peak_i]} ({monthly[peak_i]:.0f} kWh/kWp)"))
        if low_i >= 0:
            pairs.append(("Low month", f"{MONTHS_SHORT[low_i]} ({monthly[low_i]:.0f} kWh/kWp)"))
        story.append(section_hdr("SCREENING SUMMARY", st))
        story.append(Spacer(1, 0.1 * cm))
        story.append(lp(
            "Early-stage yield snapshot — comparable to Aurora / DNV / PVsyst headline "
            "results, not a bankable loss study.", st["muted"]))
        story.append(Spacer(1, 0.12 * cm))
        story.append(_metrics_grid(pairs, st))
        story.append(Spacer(1, 0.35 * cm))

    # --- Solar resource ---
    story.append(section_hdr("SOLAR RESOURCE", st))
    story.append(Spacer(1, 0.12 * cm))
    story.append(_metrics_grid([
        ("GHI (horizontal)", f"{_fmt_num(solar.get('ghi'))} kWh/m²/yr"),
        ("DNI (direct normal)", f"{_fmt_num(solar.get('dni'))} kWh/m²/yr"),
        ("DHI (diffuse horizontal)", f"{_fmt_num(solar.get('dhi'))} kWh/m²/yr"),
    ], st))
    story.append(Spacer(1, 0.35 * cm))

    # --- POA irradiance (mount-filtered) ---
    poa_pairs = []
    if "1P Fixed" in configs and _matches_filter("1P Fixed", mount_filter):
        poa_pairs.append(("POA — Fixed Tilt (1P)",
                          f"{_fmt_num(configs['1P Fixed'].get('h_y', configs['1P Fixed'].get('annual_ghi')))} kWh/m²/yr"))
    if "1P Tracker" in configs and _matches_filter("1P Tracker", mount_filter):
        poa_pairs.append(("POA — Single-Axis Tracker (1P)",
                          f"{_fmt_num(configs['1P Tracker'].get('h_y', configs['1P Tracker'].get('annual_ghi')))} kWh/m²/yr"))
    if poa_pairs:
        story.append(section_hdr("PERFORMANCE — PLANE-OF-ARRAY IRRADIANCE", st))
        story.append(Spacer(1, 0.12 * cm))
        story.append(_metrics_grid(poa_pairs, st, cols=2))
        story.append(Spacer(1, 0.35 * cm))

    # --- Losses breakdown (best config) ---
    if best_cfg and best_key:
        suffix = " (selected)" if best_key == selected_config_key else " (best specific yield)"
        story.append(section_hdr(f"LOSSES BREAKDOWN — {best_key}{suffix}", st))
        story.append(Spacer(1, 0.12 * cm))
        story.append(_metrics_grid([
            ("Shading", _fmt_loss(best_cfg.get("shading"))),
            ("Temperature", _fmt_loss(best_cfg.get("l_tg"))),
            ("Soiling", _fmt_loss(best_cfg.get("soiling_loss"))),
            ("Total loss", _fmt_loss(best_cfg.get("l_total", best_cfg.get("total_loss")))),
        ], st, cols=4))
        story.append(Spacer(1, 0.1 * cm))
        story.append(lp(
            "Temperature is PVGIS physics-based. Total loss combines shading, soiling, "
            "system losses, temperature, AOI, and spectral where available.", st["muted"]))
        story.append(Spacer(1, 0.3 * cm))

    # --- Configuration comparison ---
    story.append(section_hdr("CONFIGURATION COMPARISON", st))
    story.append(Spacer(1, 0.12 * cm))
    head = ["Configuration", "GCR", "Shading", "Total loss", "POA irr.", "Spec. yield", "Annual MWh", "PR", "CF"]
    rows = [[lp(h, st["white"]) for h in head]]
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
        ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.3, BORDER),
        ("FONTSIZE", (0, 0), (-1, -1), 7.5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LGRAY]),
    ]
    white_hdr = ParagraphStyle("wh", parent=st["body"], fontSize=7.5, textColor=colors.white, fontName="Helvetica-Bold")
    rows[0] = [lp(h, white_hdr) for h in head]
    for ri, k in enumerate(visible_keys, start=1):
        r = configs[k]
        mwh = (selected_dc_kwp * float(r.get("spec_y") or 0) / 1000.0) if selected_dc_kwp else None
        badge = ""
        if k == best_key:
            badge += "  [Best]"
        if k == selected_config_key:
            badge += "  [Sel.]"
        small = ParagraphStyle("sm", parent=st["body"], fontSize=7.5, leading=9.5)
        rows.append([
            lp(_disp_name(r, k) + badge, small),
            lp(f"{float(r.get('gcr') or 0):.2f}", small),
            lp(_fmt_loss(r.get("shading")), small),
            lp(_fmt_loss(r.get("l_total", r.get("total_loss"))), small),
            lp(_fmt_num(r.get("h_y")), small),
            lp(f"{float(r.get('spec_y') or 0):.0f}", small),
            lp(_fmt_num(mwh) if mwh is not None else "—", small),
            lp(f"{float(r['pr']):.1f}%" if r.get("pr") is not None else "—", small),
            lp(f"{float(r['cf']):.1f}%" if r.get("cf") is not None else "—", small),
        ])
        if k == selected_config_key:
            style.append(("BACKGROUND", (0, ri), (-1, ri), colors.HexColor("#e8f5ee")))
    cmp_tbl = Table(rows, colWidths=[4.6 * cm, 1.3 * cm, 1.5 * cm, 1.6 * cm, 1.6 * cm, 1.9 * cm, 1.7 * cm, 1.4 * cm, 1.4 * cm])
    cmp_tbl.setStyle(TableStyle(style))
    story.append(cmp_tbl)
    story.append(Spacer(1, 0.3 * cm))

    # --- Cross-module yield reference ---
    if cross.get("screening_fixed") is not None or cross.get("screening_tracker") is not None:
        def _delta(a, b):
            try:
                return f" ({((float(b) - float(a)) / float(a) * 100):.1f}%)" if a and b else ""
            except (TypeError, ValueError, ZeroDivisionError):
                return ""
        sf, af = cross.get("screening_fixed"), cross.get("analysis_fixed")
        stk, atk = cross.get("screening_tracker"), cross.get("analysis_tracker")
        story.append(Paragraph(
            f"<b>Cross-module yield reference.</b> SiteIQ screening vs YieldIQ analysis (1P): "
            f"Fixed {_fmt_num(sf)} &#8594; {_fmt_num(af)} kWh/kWp/yr{_delta(sf, af)} &#183; "
            f"Tracker {_fmt_num(stk)} &#8594; {_fmt_num(atk)} kWh/kWp/yr{_delta(stk, atk)}",
            st["muted"]))
        story.append(Spacer(1, 0.25 * cm))

    # --- Tracker gain ---
    # Each gain is tracker minus the matched fixed-tilt config at the SAME GCR and
    # losses (e.g. 2P Tracker vs 2P Fixed). Spell out both endpoints so the baseline
    # is verifiable — it differs from the cross-module reference above, which uses
    # the 1P configuration at the default GCR rather than the project GCR.
    tg_pairs = []
    f1, t1 = configs.get("1P Fixed"), configs.get("1P Tracker")
    f2, t2 = configs.get("2P Fixed"), configs.get("2P Tracker")

    def _gain_value(fixed_cfg: Dict[str, Any], tracker_cfg: Dict[str, Any]) -> str:
        fy = float(fixed_cfg.get("spec_y") or 0)
        ty = float(tracker_cfg.get("spec_y") or 0)
        d = ty - fy
        pct = (d / fy * 100) if fy else 0.0
        gcr = fixed_cfg.get("gcr")
        gcr_txt = f" @ GCR {float(gcr):.2f}" if gcr is not None else ""
        return f"+{d:.0f} kWh/kWp/yr ({pct:.1f}%) \u00b7 SAT {ty:,.0f} vs FT {fy:,.0f}{gcr_txt}"

    if f1 and t1 and _matches_filter("1P Tracker", mount_filter):
        tg_pairs.append(("Tracker gain (1P)", _gain_value(f1, t1)))
    if f2 and t2 and _matches_filter("2P Tracker", mount_filter):
        tg_pairs.append(("Tracker gain (2P)", _gain_value(f2, t2)))
    if tg_pairs:
        story.append(section_hdr("TRACKER GAIN", st))
        story.append(Spacer(1, 0.12 * cm))
        story.append(_metrics_grid(tg_pairs, st, cols=1))
        story.append(Spacer(1, 0.1 * cm))
        story.append(lp(
            "Gain is each tracker versus the fixed-tilt configuration at the same GCR and "
            "loss assumptions. This baseline differs from the cross-module reference above "
            "(1P at default GCR), so the two fixed-tilt figures need not match.",
            st["muted"]))
        story.append(Spacer(1, 0.25 * cm))

    if mount_filter == "sat":
        story.append(lp(
            "Single-Axis Tracker: modules follow the sun on a horizontal N–S axis (0° axis tilt) — "
            "fixed optimal tilt does not apply. PVGIS two-axis irradiance is used for the tracker yield.",
            st["muted"]))
        story.append(Spacer(1, 0.25 * cm))

    # --- Monthly specific yield chart (single config, blue) ---
    chart_cfg = sel_cfg or best_cfg
    chart_key = selected_config_key if sel_cfg else best_key
    monthly = chart_cfg.get("monthly") if chart_cfg else None
    if isinstance(monthly, list) and len(monthly) == 12:
        chart_bytes = make_monthly_specific_yield_chart(monthly, _disp_name(chart_cfg, chart_key or ""))
        block = [
            section_hdr("MONTHLY SPECIFIC YIELD (kWh/kWp)", st),
            Spacer(1, 0.12 * cm),
            RLImage(io.BytesIO(chart_bytes), width=16.5 * cm, height=5.8 * cm),
            Spacer(1, 0.1 * cm),
            lp("Specific yield per month for the selected configuration (PVGIS analysis profile).", st["muted"]),
        ]
        story.append(KeepTogether(block))
        story.append(Spacer(1, 0.2 * cm))

    if yield_result.get("disclosure"):
        story.append(lp(str(yield_result["disclosure"]), st["note"]))
    if yield_result.get("raddatabase"):
        story.append(lp(f"PVGIS radiation database: {yield_result['raddatabase']}", st["muted"]))

    return story
