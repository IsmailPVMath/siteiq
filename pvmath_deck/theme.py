"""PVMath presentation brand tokens (aligned with pvmath.com / SiteIQ app)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pptx.util import Inches, Pt

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Brand:
    name: str = "PVMath"
    tagline: str = "From site to system."
    subtitle: str = "Solar Site Intelligence Platform"
    website: str = "https://pvmath.com"
    app_url: str = "https://siteiq.pvmath.com"
    email: str = "contact@pvmath.com"
    linkedin: str = "https://www.linkedin.com/company/pvmath"
    youtube: str = "https://www.youtube.com/@PVMath_Official"

    # RGB tuples 0–255
    green: tuple = (0x1D, 0x9E, 0x52)
    green_dk: tuple = (0x14, 0x5F, 0x34)
    green_lt: tuple = (0xE8, 0xF5, 0xEE)
    text: tuple = (0x1A, 0x2E, 0x1A)
    muted: tuple = (0x5A, 0x7A, 0x5A)
    border: tuple = (0xD4, 0xE8, 0xD4)
    white: tuple = (0xFF, 0xFF, 0xFF)
    placeholder_bg: tuple = (0xF0, 0xF4, 0xF0)

    font_title: str = "Calibri"
    font_body: str = "Calibri"

    slide_w: Inches = Inches(13.333)
    slide_h: Inches = Inches(7.5)
    margin: Inches = Inches(0.55)


BRAND = Brand()
