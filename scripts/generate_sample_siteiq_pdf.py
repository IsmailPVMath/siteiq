#!/usr/bin/env python3
"""Generate public sample SiteIQ PDF (Spain demo site) for pvmath.com."""

from __future__ import annotations

import io
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from pvmath_geocode import format_coords, pdf_escape
from pvmath_pdf import SITEIQ_DISCLAIMER_BODY, append_pdf_disclaimer, append_pdf_footer

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "sample-siteiq-report.pdf"

ORANGE = colors.HexColor("#e85d04")
LGRAY = colors.HexColor("#f5f7f5")
BORDER = colors.HexColor("#d4e0d4")
DARK = colors.HexColor("#1a2e1a")
MUTED = colors.HexColor("#5a7a5a")


def _lp(text, bold=False, size=8.5):
    styles = getSampleStyleSheet()
    return Paragraph(
        pdf_escape(str(text)),
        ParagraphStyle(
            "lp",
            parent=styles["Normal"],
            fontSize=size,
            fontName="Helvetica-Bold" if bold else "Helvetica",
            textColor=DARK,
            leading=11,
        ),
    )


def build_sample_pdf() -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, rightMargin=2 * cm, leftMargin=2 * cm,
                            topMargin=2 * cm, bottomMargin=2 * cm)
    story = []

    hdr = Table([[
        Paragraph("SITEIQ — SITE ASSESSMENT REPORT (SAMPLE)",
                  ParagraphStyle("ht", fontSize=13, fontName="Helvetica-Bold",
                                   textColor=colors.white, leading=16)),
        Paragraph("PVMath · pvmath.com",
                  ParagraphStyle("hs", fontSize=8.5, textColor=colors.HexColor("#ffd0b5"),
                                   alignment=2, leading=12)),
    ]], colWidths=["63%", "37%"])
    hdr.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), ORANGE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 13),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 13),
        ("LEFTPADDING", (0, 0), (-1, -1), 14),
        ("RIGHTPADDING", (0, 0), (-1, -1), 14),
    ]))
    story += [hdr, Spacer(1, 0.35 * cm)]

    lat, lon = 38.2, -2.5
    rows = [
        [_lp("Project Name", bold=True), _lp("Castilla-La Mancha Demo (187 ha)")],
        [_lp("Location", bold=True), _lp("Castilla-La Mancha, Spain")],
        [_lp("Coordinates", bold=True), _lp(format_coords(lat, lon))],
        [_lp("Site Area", bold=True), _lp("187 ha")],
        [_lp("Land Use / Mounting", bold=True), _lp("Standard · Fixed Tilt")],
        [_lp("Report Date", bold=True), _lp(datetime.now().strftime("%d.%m.%Y"))],
        [_lp("Prepared by", bold=True), _lp("PVMath — Sample Report")],
    ]
    t = Table(rows, colWidths=[5 * cm, 12 * cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), LGRAY),
        ("GRID", (0, 0), (-1, -1), 0.5, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ]))
    story += [t, Spacer(1, 0.4 * cm)]

    metrics = [
        ["Metric", "Value", "Rating"],
        ["Annual GHI", "1,842 kWh/m²/yr", "High"],
        ["In-plane irradiation", "2,109 kWh/m²/yr", "High"],
        ["Mean slope", "3.2%", "Low"],
        ["Max slope", "4.8%", "Acceptable"],
        ["Flood risk", "Low", "Low"],
        ["Est. DC capacity (1P FT)", "75–105 MWp", "Screening band"],
        ["PVMath Score", "82 / 100", "Very Good"],
    ]
    mt = Table([[ _lp(c, bold=(i == 0)) for c in row] for i, row in enumerate(metrics)],
               colWidths=[5.5 * cm, 5.5 * cm, 5 * cm])
    mt.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), ORANGE),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LGRAY]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story += [mt, Spacer(1, 0.35 * cm)]

    story.append(_lp(
        "Representative screening output for a 187 ha site in southern Spain. "
        "Values match the public demo on pvmath.com. For a live report on your site, "
        "register free at siteiq.pvmath.com.",
        size=8,
    ))
    append_pdf_disclaimer(story, SITEIQ_DISCLAIMER_BODY)
    append_pdf_footer(
        story, "SiteIQ (sample)",
        data_sources="PVGIS JRC, EU-DEM / SRTM (OpenTopoData), OpenStreetMap.",
        note="Sample report for marketing — not project-specific. ",
        muted_color=MUTED, border_color=BORDER,
    )
    doc.build(story)
    return buf.getvalue()


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    data = build_sample_pdf()
    OUT.write_bytes(data)
    print(f"Wrote {OUT} ({len(data) // 1024} KB)")


if __name__ == "__main__":
    main()
