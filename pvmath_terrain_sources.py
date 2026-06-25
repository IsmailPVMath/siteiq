"""Shared terrain source routing and metadata for PVMath modules."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class TerrainSource(str, Enum):
    COPERNICUS_EEA10 = "copernicus_eea10"
    USGS_3DEP = "usgs_3dep"
    FABDEM = "fabdem"
    COPERNICUS_GLO30 = "copernicus_glo30"
    SURVEY_UPLOAD = "survey_upload"


@dataclass(frozen=True)
class TerrainRoute:
    source: TerrainSource
    region: str
    preferred_resolution_m: float
    fallback_sources: tuple[TerrainSource, ...] = ()
    disclaimer: str = ""
    notes: str = ""


def in_europe_bounds(lat: float, lon: float) -> bool:
    """Broad EU screening bounds used across SiteIQ/TopoIQ."""
    return 34 <= lat <= 72 and -25 <= lon <= 45


def in_usa_bounds(lat: float, lon: float) -> bool:
    """Approximate USA screening bounds for 3DEP routing."""
    return 18 <= lat <= 72 and -171 <= lon <= -66


def select_terrain_route(
    lat: float,
    lon: float,
    preferred_source: TerrainSource | None = None,
) -> TerrainRoute:
    """Pick the default terrain source path for a project coordinate."""
    if preferred_source == TerrainSource.SURVEY_UPLOAD:
        return TerrainRoute(
            source=TerrainSource.SURVEY_UPLOAD,
            region="manual",
            preferred_resolution_m=1.0,
            disclaimer="User survey upload overrides public DEM sources.",
            notes="Stub only: survey upload pipeline is not implemented yet.",
        )

    if in_europe_bounds(lat, lon):
        return TerrainRoute(
            source=TerrainSource.COPERNICUS_EEA10,
            region="eu",
            preferred_resolution_m=10.0,
            fallback_sources=(TerrainSource.COPERNICUS_GLO30,),
            disclaimer=(
                "Europe route uses Copernicus EEA-10 where available, with "
                "fallback to coarser free DEM when required."
            ),
            notes="EU bounds route prioritizes higher-resolution Copernicus terrain.",
        )
    if in_usa_bounds(lat, lon):
        return TerrainRoute(
            source=TerrainSource.USGS_3DEP,
            region="usa",
            preferred_resolution_m=10.0,
            fallback_sources=(TerrainSource.COPERNICUS_GLO30,),
            disclaimer=(
                "USA route targets USGS 3DEP elevation services and falls back "
                "to global free DEM when point coverage is unavailable."
            ),
            notes="USGS 3DEP/EPQS coverage and quality vary by tile/location.",
        )
    return TerrainRoute(
        source=TerrainSource.FABDEM,
        region="global",
        preferred_resolution_m=30.0,
        fallback_sources=(TerrainSource.COPERNICUS_GLO30,),
        disclaimer=(
            "Global route prefers FABDEM bare-earth style surface where "
            "available, with Copernicus GLO-30 fallback."
        ),
        notes="Global coverage may use fallback DEM in regions without FABDEM service.",
    )


def route_payload(route: TerrainRoute) -> dict:
    return {
        "source": route.source.value,
        "region": route.region,
        "preferred_resolution_m": route.preferred_resolution_m,
        "fallback_sources": [s.value for s in route.fallback_sources],
        "disclaimer": route.disclaimer,
        "notes": route.notes,
    }
