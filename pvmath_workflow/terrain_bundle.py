"""TerrainIQ deliverables for the project package and on-demand CAD exports.

Default project-package ``Terrain Data/`` folder (lightweight):
  - ``{base}_reference.json`` — CRS / grid metadata
  - ``{base}_points.csv`` — UTM easting, northing, elevation at the project site
  - ``{base}_contours_georef.dxf`` — georeferenced contour DXF (UTM)

On demand (TerrainIQ sidebar — not bundled automatically):
  - LandXML surface (UTM TIN)
  - Contour DXF at local origin (metres from site reference)

NOTE: ``run_terrain_analysis`` re-fetches the DEM — the heaviest step. Package
generation runs it once for the lean bundle; on-demand exports run it again unless
we add caching later.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from pvmath_topo_engine import (
    MAX_SITE_AREA_HA,
    boundaries_union_area_ha,
    run_topo_analysis,
)
from pvmath_topo_export import (
    HAS_EZDXF,
    build_reference_json,
    epsg_utm_wgs84,
    export_dxf_contours,
    export_landxml_utm,
    export_linear_units,
    export_xyz_georef,
    latlon_to_utm,
    local_en_from_latlon,
    sanitize_topo_basename,
    utm_grids_from_latlon,
)


def run_terrain_analysis(
    polygons: List[List[Tuple[float, float]]],
    *,
    grid_m: float = 5.0,
    allow_coarsen: bool = True,
    contour_minor: float = 0.5,
    contour_major: float = 1.0,
    mask_geojson: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Run TerrainIQ on ``polygons`` (rings of (lon, lat)). Raises on failure."""
    area_ha = boundaries_union_area_ha(polygons)
    if area_ha > MAX_SITE_AREA_HA:
        raise ValueError(
            f"Site boundary is {area_ha:,.0f} ha — TerrainIQ supports up to "
            f"{MAX_SITE_AREA_HA:,} ha."
        )
    return run_topo_analysis(
        polygons=polygons,
        grid_m=float(grid_m),
        allow_coarsen=allow_coarsen,
        contour_minor=float(contour_minor),
        contour_major=float(contour_major),
        mask_geojson=mask_geojson,
    )


def _analysis_context(
    analysis: Dict[str, Any],
    *,
    project_name: str,
    country: str,
) -> Dict[str, Any]:
    bbox = analysis["bbox"]
    lat_c = float(bbox["lat_c"])
    lon_c = float(bbox["lon_c"])
    return {
        "bbox": bbox,
        "X": analysis["X"],
        "Y": analysis["Y"],
        "Z": analysis["Z"],
        "polygons": analysis["polygons"],
        "base": sanitize_topo_basename(project_name),
        "cad_units": export_linear_units(country),
        "lat_c": lat_c,
        "lon_c": lon_c,
    }


def build_terrain_package_files(
    analysis: Dict[str, Any],
    *,
    project_name: str,
    country: str = "",
    contour_minor: float = 0.5,
    contour_major: float = 1.0,
) -> Dict[str, bytes]:
    """Lean Terrain Data folder: reference JSON, UTM point CSV, georef contour DXF."""
    ctx = _analysis_context(analysis, project_name=project_name, country=country)
    base = ctx["base"]
    lat_c = ctx["lat_c"]
    lon_c = ctx["lon_c"]
    X, Y, Z = ctx["X"], ctx["Y"], ctx["Z"]

    ref_epsg = epsg_utm_wgs84(lat_c, lon_c)
    ref_utm_e, ref_utm_n, _ = latlon_to_utm(lat_c, lon_c)
    reference_json = build_reference_json(
        project_name=project_name,
        lat_c=lat_c,
        lon_c=lon_c,
        elev_c=float(analysis["elevation"]["center_elev"]),
        grid_m=float(analysis["grid_m_used"]),
        epsg=ref_epsg,
        utm_e=ref_utm_e,
        utm_n=ref_utm_n,
        parcel_count=len(analysis["polygons"]),
        analysis_mode="package",
        country=country,
        linear_units=ctx["cad_units"],
        contour_minor_m=float(contour_minor),
        contour_major_m=float(contour_major),
    )

    xyz_georef = export_xyz_georef(X, Y, Z, lat_c, lon_c, units=ctx["cad_units"])

    files: Dict[str, bytes] = {}
    if reference_json:
        files[f"{base}_reference.json"] = reference_json
    if xyz_georef:
        files[f"{base}_points.csv"] = xyz_georef
    if HAS_EZDXF:
        e_georef, n_georef, _ = utm_grids_from_latlon(X, Y, lat_c, lon_c)
        dxf_georef = export_dxf_contours(
            X, Y, Z,
            easting=e_georef, northing=n_georef,
            polygon_list=ctx["polygons"],
            lat_c=lat_c, lon_c=lon_c,
            minor_int=float(contour_minor), major_int=float(contour_major),
            georef=True, units=ctx["cad_units"],
        )
        if dxf_georef:
            files[f"{base}_contours_georef.dxf"] = dxf_georef
    return files


def build_terrain_landxml_bytes(
    analysis: Dict[str, Any],
    *,
    project_name: str,
    country: str = "",
) -> Optional[bytes]:
    """LandXML TIN surface in UTM — generated on demand only."""
    ctx = _analysis_context(analysis, project_name=project_name, country=country)
    return export_landxml_utm(
        ctx["X"], ctx["Y"], ctx["Z"],
        site_name=ctx["base"],
        lat_c=ctx["lat_c"],
        lon_c=ctx["lon_c"],
        polygon_list=ctx["polygons"],
        units=ctx["cad_units"],
    )


def build_terrain_dxf_local_bytes(
    analysis: Dict[str, Any],
    *,
    project_name: str,
    country: str = "",
    contour_minor: float = 0.5,
    contour_major: float = 1.0,
) -> Optional[bytes]:
    """Contour DXF at local origin (metres from site reference) — on demand only."""
    if not HAS_EZDXF:
        return None
    ctx = _analysis_context(analysis, project_name=project_name, country=country)
    e_local, n_local = local_en_from_latlon(ctx["X"], ctx["Y"], ctx["lon_c"], ctx["lat_c"])
    return export_dxf_contours(
        ctx["X"], ctx["Y"], ctx["Z"],
        easting=e_local, northing=n_local,
        polygon_list=ctx["polygons"],
        lat_c=ctx["lat_c"], lon_c=ctx["lon_c"],
        minor_int=float(contour_minor), major_int=float(contour_major),
        georef=False, units=ctx["cad_units"],
    )


def build_terrain_files(
    polygons: List[List[Tuple[float, float]]],
    *,
    project_name: str,
    country: str = "",
    land_use: str = "Standard",
    grid_m: float = 5.0,
    allow_coarsen: bool = True,
    contour_minor: float = 0.5,
    contour_major: float = 1.0,
    mask_geojson: Optional[Dict[str, Any]] = None,
) -> Dict[str, bytes]:
    """Run analysis and return the lean package bundle (no PDF / LandXML / local DXF)."""
    analysis = run_terrain_analysis(
        polygons,
        grid_m=grid_m,
        allow_coarsen=allow_coarsen,
        contour_minor=contour_minor,
        contour_major=contour_major,
        mask_geojson=mask_geojson,
    )
    return build_terrain_package_files(
        analysis,
        project_name=project_name,
        country=country,
        contour_minor=contour_minor,
        contour_major=contour_major,
    )
