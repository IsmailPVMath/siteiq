"""Reverse geocoding via OpenStreetMap Nominatim (shared across modules)."""
from typing import Optional
from xml.sax.saxutils import escape

import requests

_NOMINATIM_HEADERS = {"User-Agent": "SiteIQ/1.0 (pvmath.com; contact@pvmath.com)"}

_LOCALITY_KEYS = (
    "city",
    "town",
    "village",
    "hamlet",
    "suburb",
    "municipality",
    "city_district",
    "neighbourhood",
)

_DISTRICT_KEYS = (
    "state_district",
    "county",
    "district",
    "region",
)


def _dedupe_parts(parts: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for part in parts:
        text = (part or "").strip()
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
    return out


def _locality_from_addr(addr: dict) -> str:
    for key in _LOCALITY_KEYS:
        val = (addr.get(key) or "").strip()
        if val:
            return val
    return ""


def _district_from_addr(addr: dict) -> str:
    for key in _DISTRICT_KEYS:
        val = (addr.get(key) or "").strip()
        if val:
            return val
    return ""


def _country_label(country: str, country_code: str = "") -> str:
    code = (country_code or "").lower()
    if code == "us" or country in ("United States", "USA"):
        return "USA"
    if code == "gb" or country == "United Kingdom":
        return "UK"
    return country


def _label_from_address(addr: dict) -> str:
    """Build a readable label from Nominatim address components."""
    country = addr.get("country", "")
    country_code = addr.get("country_code", "")
    is_us = country in ("United States", "USA") or country_code.lower() == "us"

    if is_us:
        state = (addr.get("state") or "").strip()
        county = (addr.get("county") or "").strip() or _locality_from_addr(addr)
        parts = _dedupe_parts([county, state, _country_label(country, country_code)])
        if len(parts) >= 2:
            return ", ".join(parts)

    locality = _locality_from_addr(addr)
    district = _district_from_addr(addr)
    state = (addr.get("state") or addr.get("region") or "").strip()
    country_out = _country_label(country, country_code)

    parts = _dedupe_parts([locality, district, state, country_out])
    if len(parts) >= 2:
        return ", ".join(parts)
    if parts:
        return parts[0]
    return ""


def label_from_display_name(display: str, max_parts: int = 4) -> str:
    """Trim Nominatim search display_name — drop postcodes, dedupe segments."""
    if not display:
        return ""
    segs = [s.strip() for s in display.split(",") if s.strip()]
    trimmed: list[str] = []
    for seg in segs:
        if seg.isdigit() and len(seg) >= 4:
            continue
        trimmed.append(seg)
    parts = _dedupe_parts(trimmed)
    return ", ".join(parts[:max_parts]) if parts else display


def reverse_geocode(lat: float, lon: float) -> Optional[str]:
    """
    Resolve coordinates to a human-readable admin label (pin-level detail).
    US: 'County, State, USA'. Else: 'Locality, District, State, Country' when available.
    """
    try:
        r = requests.get(
            "https://nominatim.openstreetmap.org/reverse",
            params={"lat": lat, "lon": lon, "format": "json", "zoom": 18, "addressdetails": 1},
            headers=_NOMINATIM_HEADERS,
            timeout=10,
        )
        if r.status_code != 200:
            return None
        data = r.json()
        addr = data.get("address") or {}
        label = _label_from_address(addr)
        if label:
            return label
        display = data.get("display_name", "")
        if display:
            segs = [s.strip() for s in display.split(",") if s.strip()]
            # Drop trailing postcode-only segments where possible
            trimmed = []
            for seg in segs[:5]:
                if seg.isdigit() and len(seg) >= 4:
                    continue
                trimmed.append(seg)
            return ", ".join(trimmed[:4]) if trimmed else display
    except Exception:
        pass
    return None


def format_coords(lat: float, lon: float) -> str:
    """Signed hemisphere labels — never append °E to a negative longitude."""
    ns = "N" if lat >= 0 else "S"
    ew = "E" if lon >= 0 else "W"
    return f"{abs(lat):.5f}°{ns}, {abs(lon):.5f}°{ew}"


def pdf_escape(text: str) -> str:
    """Escape user text for ReportLab Paragraph cells."""
    return escape(str(text or ""))


def resolve_location_label(
    lat: float,
    lon: float,
    *,
    saved_label: str = "",
    country: str = "",
) -> str:
    """Human-readable location for reports — saved label, then reverse geocode, then country."""
    label = (saved_label or "").strip()
    if label:
        return label
    label = reverse_geocode(lat, lon) or ""
    if label:
        return label
    return (country or "").strip()
