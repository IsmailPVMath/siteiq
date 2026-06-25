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

    def _ring_latlon(ring_lonlat: list) -> list:
        boundary = [{"lat": lat, "lon": lon} for lon, lat in ring_lonlat]
        if boundary and boundary[0] == boundary[-1] and len(boundary) > 3:
            boundary = boundary[:-1]
        return boundary

    parcels = []
    for idx, feat in enumerate(candidates):
        ring = _ring_latlon(feat["coords"])
        if len(ring) < 3:
            continue
        parcels.append(
            {
                "id": f"kml_{idx}",
                "name": feat.get("display_name") or feat.get("name") or f"Parcel {idx + 1}",
                "full_name": feat.get("name") or "",
                "layer_group": feat.get("layer_group") or "",
                "area_ha": round(float(feat.get("area_ha") or 0), 2),
                "boundary": ring,
                "point_count": len(ring),
                "is_primary": bool(feat.get("is_primary", True)),
            }
        )

    if not parcels:
        raise HTTPException(status_code=422, detail="No polygon found in KML/KMZ")

    best = max(parcels, key=lambda p: p["area_ha"])
    clat = sum(p["lat"] for p in best["boundary"]) / len(best["boundary"])
    clon = sum(p["lon"] for p in best["boundary"]) / len(best["boundary"])

    return {
        "name": best["name"] or "Uploaded boundary",
        "area_ha": best["area_ha"],
        "lat": clat,
        "lon": clon,
        "boundary": best["boundary"],
        "point_count": best["point_count"],
        "parcels": parcels,
    }
