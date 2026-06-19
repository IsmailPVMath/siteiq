"""Grouped, collapsible boundary checklist for Project Setup and TopoIQ."""
import re
import streamlit as st
from pvmath_kml import group_boundaries_by_layer, apply_site_areas_only_selection


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (text or "layer").lower())[:48]


def _layer_all_on(items: list) -> bool:
    return all(bool(b.get("enabled", True)) for b in items)


def _clear_widget_keys(key_prefix: str, all_bounds: list, groups: list) -> None:
    """Drop cached checkbox state so widgets re-read the boundary data model."""
    for b in all_bounds:
        st.session_state.pop(f"{key_prefix}_en_{b['id']}", None)
    for layer_name, _items in groups:
        st.session_state.pop(f"{key_prefix}_layer_{_slug(layer_name)}", None)
        st.session_state.pop(f"{key_prefix}_layer_prev_{_slug(layer_name)}", None)


def _set_group_enabled(items: list, enabled: bool) -> None:
    for b in items:
        b["enabled"] = enabled


def _apply_layer_widget_to_data(
    key_prefix: str,
    slug: str,
    items: list,
    *,
    want: bool,
    all_on: bool,
    prev_all_on: bool,
) -> bool:
    """
    Reconcile layer checkbox vs parcel data.
    Returns True if children were rewritten and the page should rerun.
    """
    if want == all_on:
        return False

    layer_key = f"{key_prefix}_layer_{slug}"

    # Layer box changed (not a lone child toggle) → apply to the whole group.
    if want != prev_all_on:
        _set_group_enabled(items, want)
        for b in items:
            st.session_state.pop(f"{key_prefix}_en_{b['id']}", None)
        return True

    # A child parcel changed — update the layer indicator only.
    st.session_state[layer_key] = all_on
    return False


def _layer_expanded_default(layer_name: str, parcel_count: int) -> bool:
    key = re.sub(r"[^a-z]", "", (layer_name or "").lower())
    if key in ("projectboundary", "siteboundary", "projectsite"):
        return True
    return parcel_count <= 2


def render_grouped_boundary_manager(
    *,
    all_bounds: list,
    visible_bounds: list,
    area_fn,
    key_prefix: str,
    on_clear_all,
    smart_select_fn=None,
):
    """
    Collapsible KMZ layer tree with per-layer and per-parcel checkboxes.
    Summary and action buttons stay above the tree.
    """
    if not visible_bounds:
        return []

    groups = group_boundaries_by_layer(visible_bounds)

    qa, qb, qc = st.columns(3)
    if qa.button("✓ Enable all", use_container_width=True, key=f"{key_prefix}_en_all"):
        for b in visible_bounds:
            b["enabled"] = True
        _clear_widget_keys(key_prefix, all_bounds, groups)
        st.rerun()
    if qb.button("Site areas only", use_container_width=True, key=f"{key_prefix}_en_smart"):
        if smart_select_fn:
            smart_select_fn(all_bounds, visible_bounds)
        else:
            apply_site_areas_only_selection(all_bounds)
        _clear_widget_keys(key_prefix, all_bounds, groups)
        st.rerun()
    if qc.button("Clear all", use_container_width=True, key=f"{key_prefix}_clr_all"):
        on_clear_all()
        _clear_widget_keys(key_prefix, all_bounds, groups)
        st.rerun()

    enabled = [b for b in all_bounds if b.get("enabled")]
    if enabled:
        total_ha = sum(area_fn(b["coords"]) for b in enabled)
        st.success(
            f"**{len(enabled)}** parcel{'s' if len(enabled) != 1 else ''} selected "
            f"· **{total_ha:,.1f} ha** combined"
        )
    else:
        st.warning("No parcels selected — check at least one layer or parcel.")

    st.caption(
        "**Enable all** — every visible parcel. **Site areas only** — Project Boundary / site fence "
        "layers (unchecks buildable area, laydown, etc.). **Clear all** — remove loaded boundaries. "
        "Use the box beside each **layer** to include or exclude a whole group."
    )

    remove_ids = []
    for layer_name, items in groups:
        slug = _slug(layer_name)
        layer_ha = sum(area_fn(b["coords"]) for b in items)
        all_on = _layer_all_on(items)
        expanded = _layer_expanded_default(layer_name, len(items))
        layer_key = f"{key_prefix}_layer_{slug}"
        prev_key = f"{key_prefix}_layer_prev_{slug}"
        prev_all_on = bool(st.session_state.get(prev_key, all_on))

        if layer_key not in st.session_state:
            st.session_state[layer_key] = all_on
        elif _apply_layer_widget_to_data(
            key_prefix,
            slug,
            items,
            want=bool(st.session_state[layer_key]),
            all_on=all_on,
            prev_all_on=prev_all_on,
        ):
            st.session_state[prev_key] = all_on
            st.rerun()

        st.session_state[prev_key] = all_on

        hdr_cb, hdr_tree = st.columns([0.055, 0.945])
        with hdr_cb:
            st.checkbox(
                "layer",
                key=layer_key,
                label_visibility="collapsed",
            )

        with hdr_tree:
            with st.expander(
                f"**{layer_name}** — {len(items)} parcel{'s' if len(items) != 1 else ''} "
                f"· {layer_ha:,.1f} ha",
                expanded=expanded,
            ):
                for b in items:
                    area = area_fn(b["coords"])
                    parcel_label = b.get("name", "Unnamed")
                    prefix = f"{layer_name} / "
                    if parcel_label.startswith(prefix):
                        parcel_label = parcel_label[len(prefix):]
                    parcel_key = f"{key_prefix}_en_{b['id']}"
                    desired = bool(b.get("enabled", True))
                    st.session_state[parcel_key] = desired
                    row_cb, row_txt, row_rm = st.columns([0.06, 0.84, 0.10])
                    with row_cb:
                        b["enabled"] = st.checkbox(
                            "on",
                            key=parcel_key,
                            label_visibility="collapsed",
                        )
                    with row_txt:
                        st.markdown(
                            f"{parcel_label} · {area:,.1f} ha · {len(b['coords'])} vertices"
                        )
                    with row_rm:
                        if st.button(
                            "✕", key=f"{key_prefix}_rm_{b['id']}", help="Remove parcel"
                        ):
                            remove_ids.append(b["id"])

    return remove_ids
