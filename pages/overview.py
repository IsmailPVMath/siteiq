"""
pages/overview.py — PVMath account Overview
A stats landing page: how many projects you've saved and how many analyses
you've run across modules. "My Projects" remains the detailed project list —
this page is the at-a-glance summary + quick actions, so the two no longer
show the same thing.
"""

import streamlit as st
from pvmath_auth import list_projects, get_usage
from pvmath_styles import inject_styles

_uid   = st.session_state.get("pvm_user_id", "")
_email = st.session_state.get("pvm_email", "")

inject_styles(accent="#1d9e52", accent_light="#e2ede2")

st.markdown("""
<style>
.ov-stat-card {
    background:#fff; border:1.5px solid #d4e8d4; border-radius:12px;
    padding:1.3rem 1.4rem; text-align:center;
    box-shadow:0 1px 6px rgba(0,0,0,0.05);
}
.ov-stat-num { font-size:2.1rem; font-weight:800; color:#1a2e1a; line-height:1.1; }
.ov-stat-lbl { font-size:0.82rem; color:#5a7a5a; margin-top:0.3rem; font-weight:600; }
.ov-module-row { font-size:0.85rem; color:#5a7a5a; margin-top:0.5rem; }
.ov-module-row b { color:#1a2e1a; }
</style>
""", unsafe_allow_html=True)

st.markdown(f"""
<div style="padding:1.5rem 0 0.5rem 0;border-bottom:2px solid #e8f5ee;margin-bottom:1.5rem;">
  <div style="font-size:0.75rem;font-weight:700;text-transform:uppercase;
              letter-spacing:0.12em;color:#1d9e52;margin-bottom:0.3rem;">Overview</div>
  <h1 style="font-size:2rem;font-weight:800;color:#1a2e1a;margin:0 0 0.3rem 0;">Welcome back</h1>
  <p style="color:#5a7a5a;font-size:1rem;margin:0;">{_email}</p>
</div>
""", unsafe_allow_html=True)

if not _uid:
    st.info("Sign in to see your account overview.")
    st.stop()

with st.spinner("Loading your stats…"):
    _rows = list_projects(_uid)
    _siteiq_n  = get_usage(_uid, "siteiq")
    _topoiq_n  = get_usage(_uid, "topoiq")
    _yieldiq_n = get_usage(_uid, "yieldiq")

_project_count  = len(_rows)
_analysis_total = _siteiq_n + _topoiq_n + _yieldiq_n

c1, c2 = st.columns(2)
with c1:
    st.markdown(f"""
    <div class="ov-stat-card">
      <div class="ov-stat-num">{_project_count}</div>
      <div class="ov-stat-lbl">Projects saved</div>
    </div>
    """, unsafe_allow_html=True)
with c2:
    st.markdown(f"""
    <div class="ov-stat-card">
      <div class="ov-stat-num">{_analysis_total}</div>
      <div class="ov-stat-lbl">Analyses run (all modules)</div>
      <div class="ov-module-row">
        <b>{_siteiq_n}</b> SiteIQ &nbsp;·&nbsp; <b>{_topoiq_n}</b> TopoIQ &nbsp;·&nbsp; <b>{_yieldiq_n}</b> YieldIQ
      </div>
    </div>
    """, unsafe_allow_html=True)

st.markdown("<div style='margin-top:1.5rem;'></div>", unsafe_allow_html=True)

_a1, _a2, _a3 = st.columns(3)
with _a1:
    if st.button("+ New Project", use_container_width=True, type="primary"):
        for _k in [
            "pvm_project", "pvm_project_row_id", "proj_mode_sel",
            "proj_pin_lat", "proj_pin_lon",
            "proj_map_center", "proj_map_zoom", "proj_last_search",
            "proj_polygon_draft", "proj_polygon_cleared", "proj_edit_mode",
            "map_center", "map_zoom", "map_lat", "map_lon", "last_map_search",
        ]:
            st.session_state.pop(_k, None)
        st.switch_page("pages/project.py")
with _a2:
    if st.button("View My Projects", use_container_width=True):
        st.switch_page("pages/my_projects.py")
with _a3:
    if _project_count and st.button("Continue last project", use_container_width=True):
        st.switch_page("pages/project.py")

if _project_count == 0:
    st.markdown("<div style='margin-top:1rem;'></div>", unsafe_allow_html=True)
    st.caption("No projects yet — use **+ New Project** above to set up your first site.")
