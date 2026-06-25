"""KML/KMZ boundary upload for React map workflow."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from api.deps import get_current_user
from pvmath_kml import parse_kml_features, parse_kmz_features
from pvmath_supabase import AuthUser

router = APIRouter(tags=["boundary"])

_MAX_BYTES = 8 * 1024 * 1024


def _features_from_upload(raw: bytes, filename: str) -> list:
    name = (filename or "").lower()
    if name.endswith(".kmz"):
        return parse_kmz_features(raw)
    return parse_kml_features(raw)


@router.post("/boundary/parse")
async def parse_boundary(
    file: UploadFile = File(...),
    _user: AuthUser = Depends(get_current_user),
):
    raw = await file.read()
    if len(raw) > _MAX_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 8 MB)")
    if not raw:
        raise HTTPException(status_code=400, detail="Empty file")

    features = _features_from_upload(raw, file.filename or "")
    candidates = [f for f in features if f.get("coords") and len(f["coords"]) >= 3]
    if not candidates:
        raise HTTPException(status_code=422, detail="No polygon found in KML/KMZ")

    best = max(candidates, key=lambda f: float(f.get("area_ha") or 0))
    ring_lonlat = best["coords"]
    boundary = []
    for lon, lat in ring_lonlat:
        boundary.append({"lat": lat, "lon": lon})
    if boundary and boundary[0] == boundary[-1] and len(boundary) > 3:
        boundary = boundary[:-1]

    clat = sum(p["lat"] for p in boundary) / len(boundary)
    clon = sum(p["lon"] for p in boundary) / len(boundary)

    return {
        "name": best.get("display_name") or best.get("name") or "Uploaded boundary",
        "area_ha": round(float(best.get("area_ha") or 0), 2),
        "lat": clat,
        "lon": clon,
        "boundary": boundary,
        "point_count": len(boundary),
    }
