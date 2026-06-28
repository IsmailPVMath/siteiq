"""YieldIQ PDF section for the unified PVMath report."""

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
from reportlab.platypus import Image as RLImage, Spacer, Table, TableStyle

from pvmath_capacity import format_mwh_range, format_mwp_range
from pvmath_reports.common import ACCENT, BORDER, DARK, LGRAY, MUTED, base_styles, lp, module_divider, section_hdr
from pvmath_yield import CONFIG_ORDER, config_display_name, format_loss_pct, format_pvgis_total_loss

CHART_COLORS = ["#e85d04", "#c24a00", "#1d9e52", "#145f34"]
_CHART_MUTED = "#5a7a5a"
_CHART_DARK = "#1a2e1a"
_CHART_BORDER = "#d4e8d4"


def make_monthly_energy_chart(configs: Dict[str, Any], best_cfg: str = "") -> bytes:
    x = np.arange(12)
    width = 0.18
    fig, ax = plt.subplots(figsize=(13, 5))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("#f5f7f5")

    for i, (cfg, color) in enumerate(zip(CONFIG_ORDER, CHART_COLORS)):
        if cfg not in configs:
            continue
        r = configs[cfg]
        cfg_mwp = r.get("mwp_mid") or (
            (r.get("mwp_lo", 0) + r.get("mwp_hi", 0)) / 2
            if r.get("mwp_lo") is not None else 1.0
        )
        monthly = r.get("monthly") or []
        vals_mwh = [float(v) * float(cfg_mwp) for v in monthly[:12]]
        offset = (i - 1.5) * width
        ax.bar(x + offset, vals_mwh, width, label=config_display_name(cfg), color=color,
               alpha=0.88, edgecolor="white", linewidth=0.5)

    ax.set_xlabel("Month", fontsize=10, labelpad=5, color=_CHART_MUTED)
    ax.set_ylabel("Energy output (MWh)", fontsize=10, labelpad=5, color=_CHART_MUTED)
    ax.set_xticks(x)
    ax.set_xticklabels(
        ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
        fontsize=9,
    )
    ax.legend(framealpha=0.9, fontsize=9, loc="upper left", ncol=2, edgecolor=_CHART_BORDER, labelcolor=_CHART_DARK)
    ax.grid(axis="y", alpha=0.25, linewidth=0.5, color=_CHART_BORDER)
    ax.spines[["top", "right"]].set_visible(False)
    title_cfg = best_cfg or (CONFIG_ORDER[0] if CONFIG_ORDER else "")
    ax.set_title(
        f"Monthly Energy Output — {title_cfg}",
        fontsize=11, fontweight="bold", pad=10, color=_CHART_DARK,
    )
    plt.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    return buf.getvalue()


def _best_config(configs: Dict[str, Any]) -> str:
    best, best_mwh = "", -1.0
    for cfg, r in configs.items():
        mwh = r.get("mwh_hi") or r.get("mwh_lo") or 0
        try:
            mwh = float(mwh)
        except (TypeError, ValueError):
            mwh = 0
        if mwh > best_mwh:
            best_mwh = mwh
            best = cfg
    return best


def build_yieldiq_flowables(
    *,
    yield_result: Optional[Dict[str, Any]],
    area_ha: float = 0.0,
) -> List:
    st = base_styles()
    story: List = []

    story.extend(module_divider())
    story.append(section_hdr("YieldIQ — Energy yield", st))
    story.append(Spacer(1, 0.2 * cm))

    if not yield_result or not yield_result.get("configs"):
        story.append(lp("YieldIQ not run — select a layout row and run yield analysis.", st["muted"]))
        return story

    configs = yield_result["configs"]
    solar_res = yield_result.get("solar_resource") or {}
    ghi = solar_res.get("ghi")
    dni = solar_res.get("dni")
    dhi = solar_res.get("dhi")
    best_cfg = _best_config(configs)

    story.append(section_hdr("SOLAR RESOURCE", st))
    story.append(Spacer(1, 0.12 * cm))
    res_tbl = Table([
        [lp("GHI (Horizontal)", st["lbl"]), lp("DNI (Direct Normal)", st["lbl"]), lp("DHI (Diffuse Horizontal)", st["lbl"])],
        [
            lp(f"{float(ghi):,.0f} kWh/m²/yr" if ghi else "—", st["body"]),
            lp(f"{float(dni):,.0f} kWh/m²/yr" if dni else "—", st["body"]),
            lp(f"{float(dhi):,.0f} kWh/m²/yr" if dhi else "—", st["body"]),
        ],
    ], colWidths=[5.57 * cm, 5.57 * cm, 5.57 * cm])
    res_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), LGRAY),
        ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.3, BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(res_tbl)
    story.append(Spacer(1, 0.35 * cm))

    _poa_fixed = configs.get("1P Fixed", {}).get("h_y")
    _poa_track = configs.get("1P Tracker", {}).get("h_y")
    story.append(section_hdr("PERFORMANCE — PLANE-OF-ARRAY IRRADIANCE", st))
    story.append(Spacer(1, 0.12 * cm))
    perf_tbl = Table([
        [lp("POA — Fixed Tilt (1P)", st["lbl"]), lp("POA — Single-Axis Tracker (1P)", st["lbl"])],
        [
            lp(f"{float(_poa_fixed):,.0f} kWh/m²/yr" if _poa_fixed else "—", st["body"]),
            lp(f"{float(_poa_track):,.0f} kWh/m²/yr" if _poa_track else "—", st["body"]),
        ],
    ], colWidths=[8.36 * cm, 8.36 * cm])
    perf_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), LGRAY),
        ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.3, BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(perf_tbl)
    story.append(Spacer(1, 0.35 * cm))

    if best_cfg and best_cfg in configs:
        b = configs[best_cfg]
        story.append(section_hdr(f"LOSSES BREAKDOWN — {best_cfg}", st))
        story.append(Spacer(1, 0.12 * cm))
        loss_tbl = Table([
            [lp("Shading", st["lbl"]), lp("Temperature", st["lbl"]), lp("Soiling", st["lbl"]), lp("Total Loss", st["lbl"])],
            [
                lp(format_loss_pct(b.get("shading")), st["body"]),
                lp(format_loss_pct(b.get("l_tg")), st["body"]),
                lp(format_loss_pct(b.get("soiling_loss")), st["body"]),
                lp(format_pvgis_total_loss(b), st["body"]),
            ],
        ], colWidths=[4.18 * cm, 4.18 * cm, 4.18 * cm, 4.18 * cm])
        loss_tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), LGRAY),
            ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
            ("INNERGRID", (0, 0), (-1, -1), 0.3, BORDER),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ]))
        story.append(loss_tbl)
        story.append(Spacer(1, 0.3 * cm))

    story.append(section_hdr("RESULTS — CONFIGURATION COMPARISON", st))
    story.append(Spacer(1, 0.12 * cm))
    hdr_row = [lp(h, st["lbl"]) for h in [
        "Configuration", "GCR", "MWp DC", "Spec. yield", "Annual MWh", "PR %",
    ]]
    rows = [hdr_row]
    for cfg in CONFIG_ORDER:
        if cfg not in configs:
            continue
        r = configs[cfg]
        rows.append([
            lp(config_display_name(cfg) + (" ★" if cfg == best_cfg else ""), st["body"]),
            lp(f"{float(r.get('gcr', 0)):.2f}", st["body"]),
            lp(format_mwp_range(r.get("mwp_lo", 0), r.get("mwp_hi", 0)), st["body"]),
            lp(f"{float(r.get('spec_y', 0)):,.0f}", st["body"]),
            lp(format_mwh_range(r.get("mwh_lo"), r.get("mwh_hi")) or "—", st["body"]),
            lp(f"{float(r.get('pr', 0)):.1f}%" if r.get("pr") else "—", st["body"]),
        ])
    cmp_tbl = Table(rows, colWidths=[4.5 * cm, 1.5 * cm, 2.5 * cm, 2.8 * cm, 2.8 * cm, 1.5 * cm])
    cmp_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.3, BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LGRAY]),
    ]))
    story.append(cmp_tbl)
    story.append(Spacer(1, 0.35 * cm))

    chart_bytes = make_monthly_energy_chart(configs, best_cfg)
    story.append(section_hdr("MONTHLY ENERGY PROFILE", st))
    story.append(Spacer(1, 0.12 * cm))
    story.append(RLImage(io.BytesIO(chart_bytes), width=16 * cm, height=6.5 * cm))
    story.append(Spacer(1, 0.35 * cm))

    if yield_result.get("disclosure"):
        story.append(lp(str(yield_result["disclosure"]), st["note"]))

    return story
