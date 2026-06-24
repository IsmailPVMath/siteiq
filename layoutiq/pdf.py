"""ReportLab PDF export for layout + BOM."""

from __future__ import annotations

import io
from datetime import date

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    HRFlowable,
    Image as RLImage,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


def build_pdf(
    project_name: str,
    layout: dict,
    bom: dict,
    chart_bytes: bytes,
    module_label: str,
    module_wp: int,
    n_portrait: int,
    pitch: float,
    setback: float,
    azimuth: float,
    mounting_type: str = "fixed_tilt",
) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )
    styles = getSampleStyleSheet()
    S = lambda name, **kw: ParagraphStyle(name, parent=styles["Normal"], **kw)
    lbl = S("lbl", fontSize=7.5, fontName="Helvetica-Bold", textColor=colors.HexColor("#145f34"))
    bod = S("bod", fontSize=9, textColor=colors.HexColor("#2a2a3a"), leading=13)
    sh = S("sh", fontSize=11, fontName="Helvetica-Bold", textColor=colors.HexColor("#145f34"), spaceAfter=5)
    nte = S("nte", fontSize=7.5, textColor=colors.HexColor("#8a8a9a"), leading=11)

    def lp(txt, style=bod):
        return Paragraph(str(txt), style)

    config_txt = (
        "SAT N-S axis"
        if mounting_type == "sat"
        else f"Fixed Tilt · Azimuth {azimuth}°"
    )
    story = []

    hdr = Table(
        [
            [
                lp("Layout report", S("ht", fontSize=15, fontName="Helvetica-Bold", textColor=colors.white)),
                lp(
                    "PVMath · Internal preview",
                    S("hs", fontSize=8.5, textColor=colors.HexColor("#d4e8d4"), alignment=TA_RIGHT),
                ),
            ]
        ],
        colWidths=["55%", "45%"],
    )
    hdr.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#145f34")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
            ]
        )
    )
    story += [hdr, Spacer(1, 0.35 * cm)]

    info = Table(
        [
            [lp("PROJECT", lbl), lp(project_name, bod), lp("DATE", lbl), lp(str(date.today()), bod)],
            [lp("MODULE", lbl), lp(module_label, bod), lp("MODULE Wp", lbl), lp(f"{module_wp} Wp", bod)],
            [
                lp("CONFIG", lbl),
                lp(f"{'1P' if n_portrait == 1 else '2P'} Portrait — {config_txt}", bod),
                lp("PITCH / SETBACK", lbl),
                lp(f"{pitch} m pitch · {setback} m setback", bod),
            ],
        ],
        colWidths=[2.5 * cm, 6.5 * cm, 3 * cm, 6 * cm],
    )
    info.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#e8f5ee")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#1d9e52")),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story += [info, Spacer(1, 0.4 * cm)]

    story.append(lp("Layout schematic", sh))
    story.append(RLImage(io.BytesIO(chart_bytes), width=16 * cm, height=12 * cm))
    story += [Spacer(1, 0.4 * cm)]

    story.append(lp("Bill of materials (preliminary)", sh))
    bom_rows = [[lp("Item", lbl), lp("Value", lbl)]]
    for k, v in bom.items():
        bom_rows.append([lp(k, bod), lp(v, bod)])
    bom_tbl = Table(bom_rows, colWidths=[9 * cm, 9 * cm])
    bom_tbl.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8f5ee")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#1d9e52")),
                ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#d4e8d4")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f7f5")]),
            ]
        )
    )
    story += [
        bom_tbl,
        Spacer(1, 0.4 * cm),
        HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#d4e8d4")),
        Spacer(1, 0.25 * cm),
    ]

    story.append(
        lp(
            "Internal preview — row sweep on flat boundary (no DEM yet). "
            "BOM quantities are preliminary estimates. Verify before use in proposals.",
            nte,
        )
    )

    doc.build(story)
    buf.seek(0)
    return buf.read()
