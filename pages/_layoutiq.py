"""
Admin-only layout module — not linked in sidebar.
Bookmark: https://siteiq.pvmath.com/LayoutIQ
"""

from __future__ import annotations

import math
import re

import pandas as pd
import streamlit as st

from layoutiq import (
    MODULE_PRESETS,
    build_pdf,
    compute_bom,
    load_project_context,
    make_layout_drawing,
    parse_dxf,
    parse_kml,
    parse_pasted,
    run_layout,
)
from pvmath_auth import can_access_layoutiq

if not can_access_layoutiq(
    st.session_state.get("pvm_user_id", ""),
    st.session_state.get("pvm_email", ""),
):
    st.error("Not available.")
    st.stop()

st.markdown(
    """
<style>
html, body, [class*="css"] {
    font-family:'Inter','Segoe UI',system-ui,sans-serif !important;
}
.liq-section {
    font-size:1.05rem; font-weight:700; color:#145f34;
    border-bottom:2px solid #d4e8d4; padding-bottom:0.4rem;
    margin:1.4rem 0 0.9rem 0;
}
</style>
""",
    unsafe_allow_html=True,
)

st.markdown(
    '<div class="liq-section">Internal — row layout + BOM</div>',
    unsafe_allow_html=True,
)

_ctx = load_project_context(st.session_state)
if _ctx["latlons"]:
    st.success(
        f"Project boundary loaded ({_ctx['source']}) — "
        f"{len(_ctx['latlons'])} vertices"
        + (" · TopoIQ data on file" if _ctx["has_topoiq"] else "")
    )
else:
    st.caption("No saved boundary — upload or paste below, or save a Full Mode project first.")

st.markdown('<div class="liq-section">Step 1 — Site boundary</div>', unsafe_allow_html=True)

input_method = st.radio(
    "Polygon input",
    ["Use saved project boundary", "Upload KML", "Upload DXF", "Paste coordinates"],
    horizontal=True,
    label_visibility="collapsed",
)

polygon_latlons = None
polygon_source = ""

if input_method == "Use saved project boundary":
    if _ctx["latlons"]:
        polygon_latlons = _ctx["latlons"]
        polygon_source = _ctx["source"]
    else:
        st.warning("Save a Full Mode project with a boundary in Project Setup first.")
elif input_method == "Upload KML":
    kml_file = st.file_uploader("KML / KMZ", type=["kml", "kmz"])
    if kml_file:
        pts = parse_kml(kml_file.read())
        if pts:
            polygon_latlons, polygon_source = pts, kml_file.name
            st.success(f"Loaded {len(pts)} vertices")
        else:
            st.error("No polygon found in file.")
elif input_method == "Upload DXF":
    dxf_file = st.file_uploader("DXF (local metres)", type=["dxf"])
    if dxf_file:
        pts, _ = parse_dxf(dxf_file.read())
        if pts:
            polygon_latlons, polygon_source = pts, dxf_file.name
            st.success(f"Loaded {len(pts)} points")
        else:
            st.error("No LWPOLYLINE found.")
else:
    paste_text = st.text_area(
        "Coordinates (lat,lon per line)",
        placeholder="48.1372, 11.5756\n48.1368, 11.5762\n...",
        height=120,
    )
    if paste_text.strip():
        pts = parse_pasted(paste_text)
        if pts:
            polygon_latlons, polygon_source = pts, "pasted"
            st.success(f"Parsed {len(pts)} vertices")
        else:
            st.error("Could not parse coordinates.")

st.markdown('<div class="liq-section">Step 2 — Module & rows</div>', unsafe_allow_html=True)

c1, c2 = st.columns(2)
with c1:
    module_preset = st.selectbox("Module preset", list(MODULE_PRESETS.keys()))
    preset_vals = MODULE_PRESETS[module_preset]
    if preset_vals:
        mod_h, mod_w, mod_wp = preset_vals["h"], preset_vals["w"], preset_vals["wp"]
    else:
        mc1, mc2, mc3 = st.columns(3)
        mod_h = mc1.number_input("Height (m)", 1.5, 3.0, 2.094, 0.001, format="%.3f")
        mod_w = mc2.number_input("Width (m)", 0.8, 1.5, 1.038, 0.001, format="%.3f")
        mod_wp = mc3.number_input("Power (Wp)", 200, 1000, 550, 5)

with c2:
    default_mount = _ctx.get("suggested_mount", "fixed_tilt")
    mounting_type = st.selectbox(
        "Mounting",
        ["fixed_tilt", "sat"],
        index=1 if default_mount == "sat" else 0,
        format_func=lambda x: "Fixed tilt" if x == "fixed_tilt" else "Single-axis tracker",
    )
    is_tracker = mounting_type == "sat"
    n_portrait = st.selectbox("Portrait", [1, 2], format_func=lambda x: f"{x}P")
    rc2, rc3, rc4 = st.columns(3)
    azimuth = (
        rc2.number_input("Azimuth (°)", 90.0, 270.0, 180.0, 1.0)
        if not is_tracker
        else 180.0
    )
    pitch = rc3.number_input(
        "Row pitch (m)",
        2.0,
        20.0,
        float(_ctx.get("suggested_pitch", 5.5 if is_tracker else 5.0)),
        0.1,
    )
    setback = rc4.number_input("Setback (m)", 0.0, 50.0, 5.0, 0.5)
    gap = st.number_input("Module gap (m)", 0.0, 0.1, 0.01, 0.005, format="%.3f")

st.markdown("**Strings / inverters**")
ic1, ic2, ic3 = st.columns(3)
mps = ic1.number_input("Modules per string", 8, 50, 28, 1)
spi = ic2.number_input("Strings per inverter", 1, 50, 4, 1)
inv_ac = ic3.number_input("Inverter AC (kW)", 10.0, 5000.0, 100.0, 10.0)

default_name = _ctx.get("project_name") or ""
project_name = st.text_input("Project name", value=default_name).strip() or "Layout project"

_row_cross = mod_w * n_portrait if is_tracker else mod_h * n_portrait
if pitch <= _row_cross:
    st.error(f"Pitch must exceed row width ({_row_cross:.2f} m).")
    st.stop()

run_btn = st.button("Generate layout + BOM", type="primary", disabled=polygon_latlons is None)

if run_btn and polygon_latlons:
    with st.spinner("Running layout…"):
        layout = run_layout(
            polygon_latlons,
            module_h=mod_h,
            module_w=mod_w,
            n_portrait=n_portrait,
            pitch=pitch,
            setback=setback,
            azimuth=azimuth,
            mounting_type=mounting_type,
            inter_gap=gap,
        )

    if layout is None:
        st.error("Layout failed — boundary too small after setback or pitch too large.")
        st.stop()

    dc_kwp = layout["total_modules"] * mod_wp / 1000
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Modules", f"{layout['total_modules']:,}")
    m2.metric("Rows", layout["total_rows"])
    m3.metric("DC", f"{dc_kwp:,.0f} kWp")
    m4.metric("Area", f"{layout['area_ha']} ha")

    module_label = module_preset if module_preset != "Custom input" else f"Custom {mod_wp} Wp"
    chart_bytes = make_layout_drawing(layout, project_name, mod_wp, azimuth)
    st.image(chart_bytes, use_container_width=True)

    bom = compute_bom(layout, mod_wp, n_portrait, mps, spi, inv_ac)
    bom_col1, bom_col2 = st.columns(2)
    bom_items = list(bom.items())
    half = math.ceil(len(bom_items) / 2)
    for col, chunk in ((bom_col1, bom_items[:half]), (bom_col2, bom_items[half:])):
        for key, val in chunk:
            ck, cv = col.columns([1.4, 1])
            ck.markdown(f"**{key}**")
            cv.markdown(val)

    with st.expander("Row breakdown"):
        st.dataframe(
            pd.DataFrame(
                {
                    "Row": range(1, len(layout["rows_data"]) + 1),
                    "Modules": [r["n_modules"] for r in layout["rows_data"]],
                    "Length (m)": [r["length_m"] for r in layout["rows_data"]],
                }
            ),
            use_container_width=True,
            height=220,
        )

    pdf_bytes = build_pdf(
        project_name,
        layout,
        bom,
        chart_bytes,
        module_label,
        mod_wp,
        n_portrait,
        pitch,
        setback,
        azimuth,
        mounting_type=mounting_type,
    )
    safe = re.sub(r"[^\w\- ]", "", project_name).strip().replace(" ", "_")
    st.download_button(
        "Download PDF",
        data=pdf_bytes,
        file_name=f"Layout_{safe}.pdf",
        mime="application/pdf",
        type="primary",
    )
