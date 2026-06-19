"""Shared session-state helpers for project lifecycle (new / open / clear)."""


# Keys removed when starting a blank project or opening a different saved project.
_PROJECT_STATE_KEYS = (
    "pvm_project",
    "pvm_project_row_id",
    "pvm_saved_snapshot",
    "proj_mode_sel",
    "proj_pin_lat",
    "proj_pin_lon",
    "proj_map_center",
    "proj_map_zoom",
    "proj_last_search",
    "proj_polygon_draft",
    "proj_polygon_cleared",
    "proj_edit_mode",
    "proj_boundaries",
    "proj_kml_upload_key",
    "proj_show_all_layers",
    "map_center",
    "map_zoom",
    "map_lat",
    "map_lon",
    "last_map_search",
    "siteiq_run_cache",
    "topoiq_run_cache",
    "siteiq_project_name",
    "siteiq_country",
    "siteiq_lat",
    "siteiq_lon",
    "siteiq_area_ha",
    "topo_boundaries",
    "topo_from_proj",
    "topo_upload_key",
    "topo_show_all_layers",
    "topo_proj_fp",
    "topo_project_name",
    "topo_country",
    "topo_center",
    "topo_zoom",
    "topo_last_search",
    "topo_last_coord",
    "topo_last_paste",
    "topo_last_draw_sig",
    "topo_analysis_mode",
    "topo_analysis_polygon",
)

# Widget key prefixes cleared so checkboxes re-sync with boundary data.
_BOUNDARY_WIDGET_PREFIXES = (
    "topo_en_",
    "topo_layer_",
    "topo_rm_",
    "proj_en_",
    "proj_layer_",
    "proj_rm_",
)


def _pop_boundary_widget_keys(session_state) -> None:
    for key in list(session_state.keys()):
        if any(key.startswith(p) for p in _BOUNDARY_WIDGET_PREFIXES):
            session_state.pop(key, None)


def clear_module_project_state(session_state, *, blank: bool = False) -> None:
    """Drop per-project module state (SiteIQ / TopoIQ / Project Setup maps)."""
    for key in _PROJECT_STATE_KEYS:
        session_state.pop(key, None)
    _pop_boundary_widget_keys(session_state)
    if blank:
        session_state["pvm_blank_project"] = True


def clear_blank_project_flag(session_state) -> None:
    session_state.pop("pvm_blank_project", None)
