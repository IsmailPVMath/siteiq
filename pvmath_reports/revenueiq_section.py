"""RevenueIQ PDF section for the unified PVMath report."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle

from pvmath_geocode import pdf_escape
from pvmath_reports.common import ACCENT, BORDER, DARK, MUTED, base_styles, lp, module_divider, section_hdr

_DISCLAIMER = (
    "RevenueIQ provides indicative financial screening only. CAPEX ranges are based on "
    "global benchmark data (2025–2026) adjusted for technology type, mount system, country, "
    "and market conditions; actual costs depend on site conditions, supply chain, and competitive "
    "EPC tender results. Revenue figures use indicative tariff and PPA benchmark rates — "
    "government auction projects must win the applicable tender round, and PPA rates depend on "
    "offtaker credit and market conditions at the time of contract. US ITC figures are indicative; "
    "eligibility and percentage depend on compliance with IRA 2022 requirements. All financial "
    "metrics (IRR, NPV, LCOE, payback) are screening-grade estimates only and are not bankable "
    "yield assessments. Engage a certified financial advisor and independent engineer before "
    "making any financial close or investment decision."
)

_COMPONENT_LABELS = {
    "pv_modules": "PV modules",
    "inverters": "Inverters / power conversion",
    "mounting_structure": "Mounting structure",
    "dc_cabling": "DC cabling + combiner",
    "ac_cabling": "AC cabling + MV transformer",
    "civil_works": "Civil works / earthworks",
    "grid_connection": "Grid connection",
    "engineering": "Engineering (FEED, detailed)",
    "permitting": "Permitting + development",
    "commissioning": "Commissioning + testing",
}


def _fmt_money(lo: float, hi: float, currency: str) -> str:
    if lo <= 0 and hi <= 0:
        return "—"
    if currency == "INR":
        return f"₹{lo / 1e7:.1f}–{hi / 1e7:.1f} Cr (€{lo / 90 / 1e6:.2f}–{hi / 90 / 1e6:.2f} M)"
    if currency == "USD":
        return f"${lo / 1e6:.2f}–${hi / 1e6:.2f} M"
    if currency == "EUR":
        return f"€{lo / 1e6:.2f}–{hi / 1e6:.2f} M"
    return f"{currency} {lo / 1e6:.2f}–{hi / 1e6:.2f} M"


def _viability_color(viability: str):
    v = (viability or "").upper()
    if v == "STRONG":
        return ACCENT, colors.HexColor("#e8f5ee")
    if v == "MARGINAL":
        return colors.HexColor("#f59e0b"), colors.HexColor("#fef9c3")
    return colors.HexColor("#dc2626"), colors.HexColor("#fee2e2")


def build_revenueiq_flowables(req: Optional[Dict[str, Any]], result: Optional[Dict[str, Any]]) -> List:
    """Return ReportLab flowables for the RevenueIQ section."""
    if not result or not result.get("success"):
        return []

    st = base_styles()
    r = result
    cur = str(r.get("local_currency") or "EUR")
    fx = float(r.get("eur_fx_rate") or 1.0)

    def eur_local(lo_eur: float, hi_eur: float) -> str:
        lo_l = lo_eur * fx
        hi_l = hi_eur * fx
        if cur == "EUR":
            return f"€{lo_eur / 1e6:.2f}–{hi_eur / 1e6:.2f} M"
        return f"€{lo_eur / 1e6:.2f}–{hi_eur / 1e6:.2f} M / {_fmt_money(lo_l, hi_l, cur)}"

    story: List = [
        *module_divider(),
        section_hdr("REVENUEIQ — INDICATIVE FINANCIAL SCREENING", st),
        Spacer(1, 0.15 * cm),
        lp("All figures are screening bands (low / high), not point estimates.", st["muted"]),
        Spacer(1, 0.2 * cm),
    ]

    # 1. CAPEX breakdown
    story.append(lp("CAPEX BREAKDOWN", st["h3"]))
    capex_rows = [
        [lp("Component", st["lbl"]), lp("Low", st["lbl"]), lp("High", st["lbl"])],
    ]
    breakdown = r.get("capex_breakdown") or {}
    for key, label in _COMPONENT_LABELS.items():
        row = breakdown.get(key) or {}
        lo_e = float(row.get("lo_eur") or 0)
        hi_e = float(row.get("hi_eur") or 0)
        lo_l = float(row.get("lo_local") or lo_e * fx)
        hi_l = float(row.get("hi_local") or hi_e * fx)
        if cur == "EUR":
            cell_lo = f"€{lo_e / 1e3:.0f} k"
            cell_hi = f"€{hi_e / 1e3:.0f} k"
        else:
            cell_lo = f"€{lo_e / 1e3:.0f} k / {cur} {lo_l / 1e3:.0f} k"
            cell_hi = f"€{hi_e / 1e3:.0f} k / {cur} {hi_l / 1e3:.0f} k"
        capex_rows.append([lp(label, st["body"]), lp(cell_lo, st["body"]), lp(cell_hi, st["body"])])
    gross_lo = float(r.get("capex_lo_eur") or 0)
    gross_hi = float(r.get("capex_hi_eur") or 0)
    capex_rows.append([
        lp("Gross total CAPEX", st["lbl"]),
        lp(eur_local(gross_lo, gross_lo), st["body"]),
        lp(eur_local(gross_hi, gross_hi), st["body"]),
    ])
    itc = float(r.get("itc_credit_eur") or 0)
    if itc > 0:
        itc_l = itc * fx
        capex_rows.append([
            lp("ITC credit (US)", st["lbl"]),
            lp(f"−€{itc / 1e6:.2f} M / −${itc_l / 1e6:.2f} M", st["body"]),
            lp("—", st["body"]),
        ])
        eff_lo = float(r.get("effective_capex_lo_eur") or 0)
        eff_hi = float(r.get("effective_capex_hi_eur") or 0)
        capex_rows.append([
            lp("Effective CAPEX (post-ITC)", st["lbl"]),
            lp(eur_local(eff_lo, eff_lo), st["body"]),
            lp(eur_local(eff_hi, eff_hi), st["body"]),
        ])
    ct = Table(capex_rows, colWidths=[7.5 * cm, 4.75 * cm, 4.75 * cm])
    ct.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.3, BORDER),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f7f5")]),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ]))
    story += [ct, Spacer(1, 0.25 * cm)]

    # 2. OPEX
    story.append(lp("ANNUAL OPEX", st["h3"]))
    opex_lo = float(r.get("opex_lo_eur_yr") or 0)
    opex_hi = float(r.get("opex_hi_eur_yr") or 0)
    opex_tbl = Table([
        [lp("Item", st["lbl"]), lp("Low / yr", st["lbl"]), lp("High / yr", st["lbl"])],
        [lp("O&M + land + insurance + asset mgmt + grid fees", st["body"]),
         lp(f"€{opex_lo / 1e3:.0f} k", st["body"]),
         lp(f"€{opex_hi / 1e3:.0f} k", st["body"])],
        [lp("Local currency", st["body"]),
         lp(f"{cur} {opex_lo * fx / 1e3:.0f} k", st["body"]),
         lp(f"{cur} {opex_hi * fx / 1e3:.0f} k", st["body"])],
    ], colWidths=[7.5 * cm, 4.75 * cm, 4.75 * cm])
    opex_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.3, BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ]))
    story += [opex_tbl, Spacer(1, 0.25 * cm)]

    # 3. Revenue
    story.append(lp("REVENUE MODEL", st["h3"]))
    rev_rows = [
        [lp("Field", st["lbl"]), lp("Value", st["body"])],
        [lp("Tariff mode", st["lbl"]), lp(str(r.get("tariff_mode") or "—"), st["body"])],
        [lp("Tariff band", st["lbl"]), lp(
            f"€{r.get('tariff_lo_eur_mwh')}–{r.get('tariff_hi_eur_mwh')}/MWh "
            f"({cur} {r.get('tariff_lo_local_mwh')}–{r.get('tariff_hi_local_mwh')}/MWh)",
            st["body"],
        )],
        [lp("Year 1 revenue band", st["lbl"]), lp(
            f"€{float(r.get('revenue_yr1_lo_eur') or 0) / 1e3:.0f}–"
            f"{float(r.get('revenue_yr1_hi_eur') or 0) / 1e3:.0f} k / yr",
            st["body"],
        )],
        [lp("25-year cumulative revenue", st["lbl"]), lp(
            f"€{float(r.get('revenue_25yr_lo_eur') or 0) / 1e6:.2f}–"
            f"{float(r.get('revenue_25yr_hi_eur') or 0) / 1e6:.2f} M",
            st["body"],
        )],
    ]
    rt = Table(rev_rows, colWidths=[5.5 * cm, 11.5 * cm])
    rt.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.3, BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ]))
    story += [rt, Spacer(1, 0.25 * cm)]

    # 4. Financial indicators
    story.append(lp("FINANCIAL INDICATORS (INDICATIVE)", st["h3"]))
    fin_rows = [
        [lp("Metric", st["lbl"]), lp("Low", st["lbl"]), lp("High", st["lbl"])],
        [lp("LCOE", st["body"]), lp(f"€{r.get('lcoe_lo_eur_mwh')}/MWh", st["body"]),
         lp(f"€{r.get('lcoe_hi_eur_mwh')}/MWh", st["body"])],
        [lp("Simple payback", st["body"]), lp(f"{r.get('payback_lo_yr')} yr", st["body"]),
         lp(f"{r.get('payback_hi_yr')} yr", st["body"])],
        [lp("Project IRR", st["body"]), lp(f"{r.get('irr_lo_pct')}%", st["body"]),
         lp(f"{r.get('irr_hi_pct')}%", st["body"])],
        [lp(f"NPV @ {r.get('wacc_pct', 6.5)}% WACC", st["body"]),
         lp(f"€{float(r.get('npv_lo_eur') or 0) / 1e6:.2f} M", st["body"]),
         lp(f"€{float(r.get('npv_hi_eur') or 0) / 1e6:.2f} M", st["body"])],
    ]
    ft = Table(fin_rows, colWidths=[5.5 * cm, 5.75 * cm, 5.75 * cm])
    ft.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.3, BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ]))
    story += [ft, Spacer(1, 0.25 * cm)]

    # 5. Sensitivity
    story.append(lp("SENSITIVITY (±10% impact on Project IRR)", st["h3"]))
    sens = r.get("sensitivity") or {}
    sens_rows = [[lp("Variable", st["lbl"]), lp("±10% shift", st["lbl"]),
                  lp("IRR Δ (pp)", st["lbl"]), lp("Flag", st["lbl"])]]
    labels = {"yield": "Energy yield (MWh/yr)", "capex": "Total CAPEX",
              "tariff": "Tariff / PPA rate", "opex": "OPEX"}
    for key, label in labels.items():
        delta = float(sens.get(key) or 0)
        flag = "Key Risk Factor" if delta > 3 else "—"
        sens_rows.append([
            lp(label, st["body"]), lp("±10%", st["body"]),
            lp(f"{delta:.1f} pp", st["body"]), lp(flag, st["body"]),
        ])
    stbl = Table(sens_rows, colWidths=[6.5 * cm, 3 * cm, 3 * cm, 4.5 * cm])
    stbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.3, BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ]))
    story += [stbl, Spacer(1, 0.25 * cm)]

    # 6. Viability card
    story.append(lp("ECONOMIC VIABILITY", st["h3"]))
    viability = str(r.get("viability") or "MARGINAL")
    v_color, v_bg = _viability_color(viability)
    note = str(r.get("viability_note") or "")
    card = Table([[
        Paragraph(
            f"<b>{pdf_escape(viability)}</b>",
            ParagraphStyle("rv", fontSize=14, fontName="Helvetica-Bold", textColor=v_color, leading=17),
        ),
    ]], colWidths=[17 * cm])
    card.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), v_bg),
        ("BOX", (0, 0), (-1, -1), 1.2, v_color),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
    ]))
    story += [card, Spacer(1, 0.1 * cm), lp(note, st["body"]), Spacer(1, 0.2 * cm)]
    story.append(lp(_DISCLAIMER, st["muted"]))
    story.append(Spacer(1, 0.3 * cm))
    return story
