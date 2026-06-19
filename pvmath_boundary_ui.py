"""Grouped, collapsible boundary checklist for Project Setup and TopoIQ."""
import re
import streamlit as st
from pvmath_kml import group_boundaries_by_layer, guess_boundary_enabled


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (text or "layer").lower())[:48]


def _pop_parcel_checkbox_keys(key_prefix: str, boundary_ids) -> None:
    """Streamlit keeps widget state by key — clear after bulk enable/disable."""
    for bid in boundary_ids:
        st.session_state.pop(f"{key_prefix}_en_{bid}", None)


def _pop_layer_checkbox_key(key_prefix: str, slug: str) -> None:
    st.session_state.pop(f"{key_prefix}_layer_{slug}", None)


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
        _pop_parcel_checkbox_keys(key_prefix, [b["id"] for b in visible_bounds])
        for layer_name, items in groups:
            _pop_layer_checkbox_key(key_prefix, _slug(layer_name))
        st.rerun()
    if qb.button("Site areas only", use_container_width=True, key=f"{key_prefix}_en_smart"):
        if smart_select_fn:
            smart_select_fn(all_bounds, visible_bounds)
        else:
            for b in all_bounds:
                b["enabled"] = guess_boundary_enabled(
                    b.get("full_name", b.get("name", "")),
                    area_fn(b["coords"]),
                )
        _pop_parcel_checkbox_keys(key_prefix, [b["id"] for b in all_bounds])
        for layer_name, items in groups:
            _pop_layer_checkbox_key(key_prefix, _slug(layer_name))
        st.rerun()
    if qc.button("Clear all", use_container_width=True, key=f"{key_prefix}_clr_all"):
        on_clear_all()
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
        "Use the box beside each **layer** to include or exclude the whole group. "
        "Expand a layer to pick individual parcels."
    )

    remove_ids = []
    for layer_name, items in groups:
        slug = _slug(layer_name)
        layer_ha = sum(area_fn(b["coords"]) for b in items)
        all_on = all(b.get("enabled", True) for b in items)
        expanded = _layer_expanded_default(layer_name, len(items))

        hdr_cb, hdr_tree = st.columns([0.055, 0.945])
        with hdr_cb:
            layer_on = st.checkbox(
                "layer",
                value=all_on,
                key=f"{key_prefix}_layer_{slug}",
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
                    row_cb, row_txt, row_rm = st.columns([0.06, 0.84, 0.10])
                    with row_cb:
                        b["enabled"] = st.checkbox(
                            "on",
                            value=b.get("enabled", True),
                            key=f"{key_prefix}_en_{b['id']}",
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

        if layer_on != all_on:
            for b in items:
                b["enabled"] = layer_on
            _pop_parcel_checkbox_keys(key_prefix, [b["id"] for b in items])
            _pop_layer_checkbox_key(key_prefix, slug)
            st.rerun()

    return remove_ids
