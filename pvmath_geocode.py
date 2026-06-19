"""Reverse geocoding via OpenStreetMap Nominatim (shared across modules)."""
from typing import Optional

import requests

_NOMINATIM_HEADERS = {"User-Agent": "SiteIQ/1.0 (pvmath.com; contact@pvmath.com)"}


def reverse_geocode(lat: float, lon: float) -> Optional[str]:
    """
    Resolve coordinates to a human-readable admin label.
    US: 'County, State, Country' when available; else best-effort display_name tail.
    """
    try:
        r = requests.get(
            "https://nominatim.openstreetmap.org/reverse",
            params={"lat": lat, "lon": lon, "format": "json", "zoom": 10},
            headers=_NOMINATIM_HEADERS,
            timeout=10,
        )
        if r.status_code != 200:
            return None
        data = r.json()
        addr = data.get("address") or {}
        country = addr.get("country", "")
        is_us = country in ("United States", "USA") or addr.get("country_code", "").lower() == "us"
        if is_us:
            state = addr.get("state", "")
            county = addr.get("county", "") or addr.get("city", "")
            parts = [p for p in (county, state, "USA") if p]
            if len(parts) >= 2:
                return ", ".join(parts)
        state = addr.get("state", "") or addr.get("region", "") or addr.get("county", "")
        parts = [p for p in (state, country) if p]
        if parts:
            return ", ".join(parts)
        display = data.get("display_name", "")
        if display:
            segs = [s.strip() for s in display.split(",")]
            return ", ".join(segs[:3]) if len(segs) > 3 else display
    except Exception:
        pass
    return None


def format_coords(lat: float, lon: float) -> str:
    """Signed hemisphere labels — never append °E to a negative longitude."""
    ns = "N" if lat >= 0 else "S"
    ew = "E" if lon >= 0 else "W"
    return f"{abs(lat):.5f}°{ns}, {abs(lon):.5f}°{ew}"
