"""Geocoding proxy (Nominatim) — correct User-Agent, no browser CORS."""

from __future__ import annotations

import requests
from fastapi import APIRouter, Depends, HTTPException, Query

from api.deps import get_current_user
from pvmath_geocode import reverse_geocode, reverse_geocode_parts
from pvmath_supabase import AuthUser

router = APIRouter(tags=["geocode"])

_HEADERS = {"User-Agent": "SiteIQ/1.0 (pvmath.com; contact@pvmath.com)"}


@router.get("/geocode/search")
def geocode_search(
    q: str = Query(..., min_length=2, max_length=200),
    _user: AuthUser = Depends(get_current_user),
):
    try:
        r = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": q, "format": "json", "limit": 5},
            headers=_HEADERS,
            timeout=12,
        )
        r.raise_for_status()
        rows = r.json()
    except requests.RequestException as exc:
        raise HTTPException(status_code=503, detail="Geocoding service unavailable") from exc

    return {
        "results": [
            {
                "lat": float(row["lat"]),
                "lon": float(row["lon"]),
                "label": row.get("display_name", ""),
            }
            for row in rows
        ]
    }


@router.get("/geocode/reverse")
def geocode_reverse(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    _user: AuthUser = Depends(get_current_user),
):
    parts = reverse_geocode_parts(lat, lon)
    return {
        "lat": lat,
        "lon": lon,
        "label": parts.get("label") or "",
        "country": parts.get("country") or "",
        "state": parts.get("state") or "",
        "city": parts.get("city") or "",
    }
