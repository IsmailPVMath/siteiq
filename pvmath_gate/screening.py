"""Pure screening helpers (no Streamlit) — extracted for FastAPI gate runs."""

from __future__ import annotations

import math

import requests

USER_AGENT = "PVMath/1.0 (pvmath.com; contact@pvmath.com)"


def _point_in_polygon(plat, plon, poly):
    n = len(poly)
    inside = False
    j = n - 1
    for i in range(n):
        lat_i, lon_i = poly[i]
        lat_j, lon_j = poly[j]
        if (lon_i > plon) != (lon_j > plon):
            x = (lat_j - lat_i) * (plon - lon_i) / ((lon_j - lon_i) or 1e-15) + lat_i
            if plat < x:
                inside = not inside
        j = i
    return inside


def _haversine_m(lat1, lon1, lat2, lon2):
    r = 6_371_000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def get_terrain_data(lat, lon, polygon=None, polygons=None, radius_km=0.5):
    """Slope/elevation screening via OpenTopoData (same logic as SiteIQ)."""
    in_europe = 34 <= lat <= 72 and -25 <= lon <= 45
    dataset = "eudem25m" if in_europe else "srtm30m"

    poly_list = []
    if polygons:
        poly_list = [p for p in polygons if p and len(p) >= 3]
    elif polygon and len(polygon) >= 3:
        poly_list = [polygon]

    headers = {"User-Agent": USER_AGENT}

    if poly_list:
        all_lats = [p[0] for poly in poly_list for p in poly]
        all_lons = [p[1] for poly in poly_list for p in poly]
        lat_min, lat_max = min(all_lats), max(all_lats)
        lon_min, lon_max = min(all_lons), max(all_lons)
        grid_n = 7
        grid_pts = []
        for i in range(grid_n):
            for j in range(grid_n):
                glat = lat_min + (lat_max - lat_min) * (i + 0.5) / grid_n
                glon = lon_min + (lon_max - lon_min) * (j + 0.5) / grid_n
                if any(_point_in_polygon(glat, glon, poly) for poly in poly_list):
                    grid_pts.append((glat, glon))
        if len(grid_pts) < 4:
            clat, clon = sum(all_lats) / len(all_lats), sum(all_lons) / len(all_lons)
            grid_pts = [(clat, clon)]
        grid_pts = grid_pts[:40]
        locations = "|".join(f"{p[0]},{p[1]}" for p in grid_pts)
        try:
            r = requests.get(
                f"https://api.opentopodata.org/v1/{dataset}",
                params={"locations": locations},
                headers=headers,
                timeout=20,
            )
            results = r.json().get("results", [])
            pts = [
                (grid_pts[i][0], grid_pts[i][1], res["elevation"])
                for i, res in enumerate(results)
                if res.get("elevation") is not None
            ]
            if len(pts) < 4:
                return {"success": False, "error": "Insufficient data"}
            slopes = []
            for i, (la1, lo1, z1) in enumerate(pts):
                nearest = sorted(
                    ((j, _haversine_m(la1, lo1, pts[j][0], pts[j][1])) for j in range(len(pts)) if j != i),
                    key=lambda x: x[1],
                )[:3]
                for j, d in nearest:
                    if d > 0:
                        slopes.append(abs(pts[j][2] - z1) / d * 100)
            if not slopes:
                return {"success": False, "error": "Insufficient data"}
            zs = [p[2] for p in pts]
            return {
                "success": True,
                "center_elev": round(zs[len(zs) // 2], 1),
                "max_slope_pct": round(max(slopes), 1),
                "mean_slope_pct": round(sum(slopes) / len(slopes), 1),
                "elevation_range": round(max(zs) - min(zs), 1),
                "sample_points": len(pts),
                "boundary_sampled": True,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    delta = radius_km / 111.0
    dist_m = radius_km * 1000.0
    dirs = [
        (1, 0), (-1, 0), (0, 1), (0, -1),
        (0.7071, 0.7071), (0.7071, -0.7071), (-0.7071, 0.7071), (-0.7071, -0.7071),
    ]
    points = [(lat, lon)] + [(lat + dy * delta, lon + dx * delta) for dy, dx in dirs]
    locations = "|".join(f"{p[0]},{p[1]}" for p in points)
    try:
        r = requests.get(
            f"https://api.opentopodata.org/v1/{dataset}",
            params={"locations": locations},
            headers=headers,
            timeout=15,
        )
        results = r.json().get("results", [])
        elevs = [res["elevation"] for res in results if res.get("elevation") is not None]
        if len(elevs) >= 5:
            center = elevs[0]
            slopes = [abs(e - center) / dist_m * 100 for e in elevs[1:]]
            return {
                "success": True,
                "center_elev": round(center, 1),
                "max_slope_pct": round(max(slopes), 1),
                "mean_slope_pct": round(sum(slopes) / len(slopes), 1),
                "elevation_range": round(max(elevs) - min(elevs), 1),
                "sample_points": len(elevs),
                "boundary_sampled": False,
            }
    except Exception as e:
        return {"success": False, "error": str(e)}
    return {"success": False, "error": "Insufficient data"}


def assess_solar(ghi: float) -> tuple[str, str]:
    if ghi >= 1300:
        return "Excellent", f"{ghi} kWh/m²/yr — premium resource"
    if ghi >= 1100:
        return "Good", f"{ghi} kWh/m²/yr — good resource"
    if ghi >= 900:
        return "Moderate", f"{ghi} kWh/m²/yr — viable, below average"
    return "Poor", f"{ghi} kWh/m²/yr — low resource"


def assess_slope(pct: float, mount_type: str = "Fixed Tilt") -> tuple[str, str]:
    tracker = mount_type == "Single-Axis Tracker"
    if tracker:
        if pct <= 3:
            return "Excellent", f"{pct}% — ideal for tracker"
        if pct <= 6:
            return "Acceptable", f"{pct}% — feasible with grading"
        if pct <= 10:
            return "Challenging", f"{pct}% — steep for trackers"
        return "Critical", f"{pct}% — likely not viable for trackers"
    if pct <= 5:
        return "Excellent", f"{pct}% — ideal for fixed tilt"
    if pct <= 10:
        return "Acceptable", f"{pct}% — feasible"
    if pct <= 15:
        return "Challenging", f"{pct}% — significant earthworks"
    return "Critical", f"{pct}% — likely not viable"


def get_flood_risk(lat: float, lon: float, elevation: float | None) -> dict:
    if elevation is None:
        risk, detail = "Unknown", "Elevation unavailable — manual flood check required"
    elif elevation < 10:
        risk, detail = "High", f"Centre {elevation} m asl — low elevation"
    elif elevation < 50:
        risk, detail = "Moderate", f"Centre {elevation} m asl — low-lying"
    elif elevation < 200:
        risk, detail = "Low-Moderate", f"Centre {elevation} m asl — moderate elevation"
    else:
        risk, detail = "Low", f"Centre {elevation} m asl — relatively elevated"
    return {
        "risk": risk,
        "detail": detail,
        "source": "OpenTopoData DEM — elevation heuristic only",
        "confidence": "Low — not official flood-zone mapping",
    }


def assess_regulatory(lat: float, lon: float, land_use: str, country: str) -> dict:
    """Light regulatory pointer — full logic stays in SiteIQ until shared module split."""
    c = (country or "").lower()
    agri = land_use == "Agri-PV"
    if any(x in c for x in ["india", "bharat"]):
        status = "MNRE / SECI auction or state DISCOM PPA"
        note = "CERC framework — contact state DISCOM for grid connectivity"
    elif any(x in c for x in ["germany", "deutschland"]):
        status = "EEG 2023 Agri-PV bonus" if agri else "EEG 2023 Freifläche tariff"
        note = "Register at Bundesnetzagentur"
    elif any(x in c for x in ["spain", "españa"]):
        status = "RESA auction / OMIE market"
        note = "CNMC / REE — competitive auction"
    else:
        status = "Check local renewable scheme"
        note = "Contact national energy regulator"
    return {"country": country or "—", "status": status, "note": note}
