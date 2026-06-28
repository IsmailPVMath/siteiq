"""Shared ReportLab styles for unified PVMath reports."""

from __future__ import annotations

from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, Table, TableStyle

from pvmath_geocode import pdf_escape

ACCENT = colors.HexColor("#1d9e52")
ACCENT_DK = colors.HexColor("#157a40")
ACCENT_HDR = colors.HexColor("#145f34")
DARK = colors.HexColor("#1a2e1a")
MUTED = colors.HexColor("#5a7a5a")
LGRAY = colors.HexColor("#f5f7f5")
BORDER = colors.HexColor("#d4e8d4")


def lp(text: str, style) -> Paragraph:
    return Paragraph(pdf_escape(str(text)), style)


def base_styles():
    base = getSampleStyleSheet()
    S = lambda name, **kw: ParagraphStyle(name, parent=base["Normal"], **kw)
    return {
        "title": S("title", fontSize=16, fontName="Helvetica-Bold", textColor=ACCENT, spaceAfter=8),
        "h2": S("h2", fontSize=12, fontName="Helvetica-Bold", textColor=DARK, spaceBefore=10, spaceAfter=6),
        "h3": S("h3", fontSize=10, fontName="Helvetica-Bold", textColor=DARK, spaceAfter=4),
        "body": S("body", fontSize=9, textColor=DARK, leading=13),
        "muted": S("muted", fontSize=8, textColor=MUTED, leading=11),
        "lbl": S("lbl", fontSize=7.5, fontName="Helvetica-Bold", textColor=MUTED),
        "white": S("white", fontSize=11, fontName="Helvetica-Bold", textColor=colors.white),
        "note": S("note", fontSize=7.5, textColor=colors.HexColor("#7a4f00"), leading=11),
    }


def section_hdr(text: str, st) -> Table:
    """Section title with green left-accent stripe (PVMath brand)."""
    t = Table(
        [[
            Paragraph("", ParagraphStyle("x", parent=st["body"])),
            Paragraph(text, ParagraphStyle(
                "sh", parent=st["h3"], fontSize=11, fontName="Helvetica-Bold",
                textColor=DARK, leading=14,
            )),
        ]],
        colWidths=[0.28 * 28.35, 16.72 * 28.35],
    )
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), ACCENT),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (1, 0), (1, -1), 8),
        ("LEFTPADDING", (0, 0), (0, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    return t


def module_banner(title: str, subtitle: str, st) -> Table:
    hdr = Table(
        [[
            lp(title, st["white"]),
            lp(subtitle, ParagraphStyle(
                "hs", parent=st["muted"], fontSize=8,
                textColor=colors.HexColor("#d4e8d4"), alignment=2,
            )),
        ]],
        colWidths=["58%", "42%"],
    )
    hdr.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), ACCENT_HDR),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 12),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
        ("LEFTPADDING", (0, 0), (-1, -1), 14),
        ("RIGHTPADDING", (0, 0), (-1, -1), 14),
    ]))
    return hdr
