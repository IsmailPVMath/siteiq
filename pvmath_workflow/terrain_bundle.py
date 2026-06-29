"""Build TerrainIQ deliverable files for bundling inside the project package ZIP.

This mirrors the standalone TerrainIQ CAD-ZIP / PDF endpoints, but returns the
files as an in-memory ``{filename: bytes}`` map so they can be dropped into a
``Terrain Data/`` folder of the project package instead of a separate download.

NOTE: ``run_topo_analysis`` re-fetches the DEM and rebuilds the grid, so this is
the heavy part of package generation — see ``build_terrain_files`` callers for
the best-effort / timeout handling.
"""

from __future__ import annotations

import io
from typing import Any, Dict, List, Optional, Tuple

from pvmath_geocode import resolve_location_label
from pvmath_terrain_report import (
    build_report_context,
    generate_pdf_report,
    render_slope_map_png,
)
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
    export_xyz_geo,
    export_xyz_georef,
    export_xyz_local,
    latlon_to_utm,
    local_en_from_latlon,
    sanitize_topo_basename,
    utm_grids_from_latlon,
)
from pvmath_yield import (
    fetch_yield_cross_ref_bundle,
    yield_cross_ref_terrainiq_text,
)


def _build_terrain_pdf(
    analysis: Dict[str, Any],
    *,
    project_name: str,
    country: str,
    land_use: str,
) -> bytes:
    bbox = analysis["bbox"]
    X = analysis["X"]
    Y = analysis["Y"]
    Z = analysis["Z"]
    terrain_meta = analysis.get("terrain_source") or {}
    slope_img_buf = render_slope_map_png(
        X,
        Y,
        Z,
        float(analysis["grid_m_used"]),
        float(bbox["south"]),
        float(bbox["north"]),
        float(bbox["west"]),
        float(bbox["east"]),
        polygon_list=analysis["polygons"],
        terrain_source_used=str(analysis.get("terrain_source_used", "")),
        terrain_disclaimer=str(terrain_meta.get("disclaimer", "")),
        tiles=analysis.get("tiles"),
    )
    slope_buf = io.BytesIO(slope_img_buf.getvalue()) if slope_img_buf else None
    if slope_buf:
        slope_buf.seek(0)
    yield_ref = fetch_yield_cross_ref_bundle(float(bbox["lat_c"]), float(bbox["lon_c"]))
    ctx = build_report_context(
        project_name=project_name,
        country=country,
        location_label=resolve_location_label(
            float(bbox["lat_c"]),
            float(bbox["lon_c"]),
            saved_label="",
            country=country,
        ),
        lat_c=float(bbox["lat_c"]),
        lon_c=float(bbox["lon_c"]),
        area_ha=float(analysis["area_ha"]),
        grid_spacing=float(analysis["grid_m_used"]),
        grid_spacing_requested=float(analysis["grid_m_requested"]),
        z_min=float(analysis["elevation"]["z_min"]),
        z_max=float(analysis["elevation"]["z_max"]),
        mean_slope=float(analysis["slope"]["mean"]),
        max_slope=float(analysis["slope"]["max"]),
        pct_over5=float(analysis["slope"]["pct_over5"]),
        pct_over10=float(analysis["slope"]["pct_over10"]),
        slope_bins=analysis["slope"]["bins"],
        slope_img_buf=slope_buf,
        land_use=land_use,
        mount_type=None,
        boundary_provenance="Project boundary (package)",
        prepared_by="PVMath",
        module_confidence="Screening-grade terrain assessment.",
        extras=analysis["extras"],
        siteiq_run_cache=None,
        project_row_id=None,
        dem_zoom=int(analysis["dem_zoom"]),
        terrain_source=analysis["terrain_source"],
        terrain_source_used=str(analysis["terrain_source_used"]),
        yield_cross_ref=yield_cross_ref_terrainiq_text(yield_ref),
    )
    pdf_bytes = generate_pdf_report(ctx)
    if not pdf_bytes:
        raise RuntimeError("PDF_GENERATION_FAILED")
    return pdf_bytes


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
    """Run TerrainIQ on ``polygons`` (rings of (lon, lat)) and return the full
    set of TerrainIQ deliverables as ``{filename: bytes}`` (no folder prefix).

    Raises on failure; callers should treat this as best-effort.
    """
    area_ha = boundaries_union_area_ha(polygons)
    if area_ha > MAX_SITE_AREA_HA:
        raise ValueError(
            f"Site boundary is {area_ha:,.0f} ha — TerrainIQ supports up to "
            f"{MAX_SITE_AREA_HA:,} ha."
        )
    analysis = run_topo_analysis(
        polygons=polygons,
        grid_m=float(grid_m),
        allow_coarsen=allow_coarsen,
        contour_minor=float(contour_minor),
        contour_major=float(contour_major),
        mask_geojson=mask_geojson,
    )

    bbox = analysis["bbox"]
    X = analysis["X"]
    Y = analysis["Y"]
    Z = analysis["Z"]
    base = sanitize_topo_basename(project_name)
    cad_units = export_linear_units(country)
    lat_c = float(bbox["lat_c"])
    lon_c = float(bbox["lon_c"])

    pdf_bytes = _build_terrain_pdf(
        analysis,
        project_name=project_name,
        country=country,
        land_use=land_use,
    )

    e_local, n_local = local_en_from_latlon(X, Y, lon_c, lat_c)
    e_georef, n_georef, _ = utm_grids_from_latlon(X, Y, lat_c, lon_c)
    lxml = export_landxml_utm(
        X, Y, Z,
        site_name=base,
        lat_c=lat_c,
        lon_c=lon_c,
        polygon_list=analysis["polygons"],
        units=cad_units,
    )
    xyz_local = export_xyz_local(X, Y, Z, lat_c, lon_c, units=cad_units)
    xyz_georef = export_xyz_georef(X, Y, Z, lat_c, lon_c, units=cad_units)
    xyz_geo = export_xyz_geo(X, Y, Z)
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
        linear_units=cad_units,
    )

    files: Dict[str, bytes] = {}
    if reference_json:
        files[f"{base}_reference.json"] = reference_json
    if pdf_bytes:
        files[f"{base}_terrain_report.pdf"] = pdf_bytes
    if lxml:
        files[f"{base}.xml"] = lxml
    if HAS_EZDXF:
        dxf_local = export_dxf_contours(
            X, Y, Z,
            easting=e_local, northing=n_local,
            polygon_list=analysis["polygons"],
            lat_c=lat_c, lon_c=lon_c,
            minor_int=float(contour_minor), major_int=float(contour_major),
            georef=False, units=cad_units,
        )
        dxf_georef = export_dxf_contours(
            X, Y, Z,
            easting=e_georef, northing=n_georef,
            polygon_list=analysis["polygons"],
            lat_c=lat_c, lon_c=lon_c,
            minor_int=float(contour_minor), major_int=float(contour_major),
            georef=True, units=cad_units,
        )
        if dxf_local:
            files[f"{base}_contours_local.dxf"] = dxf_local
        if dxf_georef:
            files[f"{base}_contours_georef.dxf"] = dxf_georef
    if xyz_local:
        files[f"{base}_local.csv"] = xyz_local
    if xyz_georef:
        files[f"{base}_georef.csv"] = xyz_georef
    if xyz_geo:
        files[f"{base}_geo.csv"] = xyz_geo
    return files
