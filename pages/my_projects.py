"""
pages/my_projects.py — PVMath "My Projects" dashboard
Lists every project the signed-in user has saved (Railway-style grid).
Opening a card loads that project into st.session_state["pvm_project"]
and jumps to the Overview/Project Setup page.
"""

import streamlit as st
from pvmath_auth import list_projects, delete_project
from pvmath_session import clear_module_project_state, clear_blank_project_flag
from pvmath_styles import inject_styles

_uid = st.session_state.get("pvm_user_id", "")

# ─── Styling ──────────────────────────────────────────────────────────────────
inject_styles(accent="#1d9e52", accent_light="#e2ede2")

st.markdown("""
<style>
.myproj-card {
    background:#fff; border:1.5px solid #d4e8d4; border-radius:12px;
    padding:1.1rem 1.2rem 0.4rem; margin-bottom:0.6rem;
    box-shadow:0 1px 6px rgba(0,0,0,0.05);
}
.myproj-name {
    font-size:1.02rem; font-weight:800; color:#1a2e1a;
    margin-bottom:0.45rem; line-height:1.3;
    overflow:hidden; text-overflow:ellipsis; white-space:nowrap;
}
.myproj-badge {
    display:inline-block; font-size:0.7rem; font-weight:700;
    padding:2px 9px; border-radius:5px; letter-spacing:0.03em;
}
.myproj-meta { font-size:0.82rem; color:#5a7a5a; margin-top:0.6rem; line-height:1.6; }
.myproj-empty {
    text-align:center; padding:3rem 1.5rem; background:#fff;
    border:1.5px dashed #c8dcc8; border-radius:14px; color:#5a7a5a;
}
</style>
""", unsafe_allow_html=True)

# ─── Header ───────────────────────────────────────────────────────────────────
st.markdown("""
<div style="padding:1.5rem 0 0.5rem 0;border-bottom:2px solid #e8f5ee;margin-bottom:1.5rem;">
  <div style="font-size:0.75rem;font-weight:700;text-transform:uppercase;
              letter-spacing:0.12em;color:#1d9e52;margin-bottom:0.3rem;">Overview</div>
  <h1 style="font-size:2rem;font-weight:800;color:#1a2e1a;margin:0 0 0.3rem 0;">My Projects</h1>
  <p style="color:#5a7a5a;font-size:1rem;margin:0;">
    Every site you've saved. Open one to keep working on it, or start a new one with
    <strong>+ New Project</strong> on Overview.
  </p>
</div>
""", unsafe_allow_html=True)

if not _uid:
    st.info("Sign in to see your saved projects.")
    st.stop()

with st.spinner("Loading your projects…"):
    _rows = list_projects(_uid)

if not _rows:
    st.markdown("""
    <div class="myproj-empty">
      <div style="font-size:1.6rem;margin-bottom:0.6rem;"><i class="fa-regular fa-folder-open"></i></div>
      <div style="font-weight:700;color:#1a2e1a;margin-bottom:0.3rem;">No projects yet</div>
      <div style="font-size:0.88rem;">Use <strong>+ New Project</strong> on Overview to set up your first site.</div>
    </div>
    """, unsafe_allow_html=True)
    st.stop()

st.caption(f"{len(_rows)} project{'s' if len(_rows) != 1 else ''}")

_COLS = 3
for _i in range(0, len(_rows), _COLS):
    _chunk = _rows[_i:_i + _COLS]
    _cols = st.columns(_COLS)
    for _j, (_col, _row) in enumerate(zip(_cols, _chunk)):
        _gidx = _i + _j
        _row_id = _row.get("id")
        _key = str(_row_id) if _row_id is not None else f"idx{_gidx}"
        _pdata = _row.get("project_data") or {}

        _name = (_pdata.get("name") or "Untitled project").strip() or "Untitled project"
        _is_full = _pdata.get("mode") == "full"
        _badge_bg, _badge_fg, _badge_txt = (
            ("#e2ede2", "#1a5c2e", "FULL MODE") if _is_full
            else ("#e2edf7", "#1565c0", "QUICK MODE")
        )
        _country = _pdata.get("country") or "—"
        _lat, _lon = _pdata.get("lat"), _pdata.get("lon")
        _coord_txt = f"{_lat:.4f}°, {_lon:.4f}°" if _lat is not None and _lon is not None else "—"
        _area = _pdata.get("area_ha")
        _area_txt = f" &nbsp;·&nbsp; {_area:g} ha" if _area else ""

        with _col:
            st.markdown(f"""
            <div class="myproj-card">
              <div class="myproj-name" title="{_name}">{_name}</div>
              <span class="myproj-badge" style="background:{_badge_bg};color:{_badge_fg};">{_badge_txt}</span>
              <div class="myproj-meta">
                <i class="fa-solid fa-earth-americas"></i> {_country}<br>
                <i class="fa-solid fa-location-dot"></i> {_coord_txt}{_area_txt}
              </div>
            </div>
            """, unsafe_allow_html=True)

            _oc, _dc = st.columns([3, 1])
            with _oc:
                if st.button("Open →", key=f"open_{_key}", use_container_width=True):
                    clear_module_project_state(st.session_state)
                    clear_blank_project_flag(st.session_state)
                    st.session_state["pvm_project"] = _pdata
                    st.session_state["pvm_project_row_id"] = _row_id
                    st.session_state["pvm_saved_snapshot"] = dict(_pdata)
                    st.switch_page("pages/project.py")
            with _dc:
                if st.button("🗑", key=f"del_{_key}", help="Delete this project", use_container_width=True):
                    st.session_state[f"confirm_del_{_key}"] = True

            if st.session_state.get(f"confirm_del_{_key}"):
                st.warning(f"Delete **{_name}**? This can't be undone.")
                _yc, _nc = st.columns(2)
                with _yc:
                    if st.button("Yes, delete", key=f"yesdel_{_key}", use_container_width=True):
                        delete_project(_uid, _row_id)
                        st.session_state.pop(f"confirm_del_{_key}", None)
                        if st.session_state.get("pvm_project_row_id") == _row_id:
                            st.session_state.pop("pvm_project", None)
                            st.session_state.pop("pvm_project_row_id", None)
                            st.session_state.pop("pvm_saved_snapshot", None)
                        st.rerun()
                with _nc:
                    if st.button("Cancel", key=f"nodel_{_key}", use_container_width=True):
                        st.session_state.pop(f"confirm_del_{_key}", None)
                        st.rerun()
