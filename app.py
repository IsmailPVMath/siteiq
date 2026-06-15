import streamlit as st
from pvmath_auth import render_auth_page, sign_out, load_project

st.set_page_config(
    page_title="PVMath — Solar Site Intelligence",
    page_icon="🌱",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Navigation (position="hidden" = we build sidebar manually) ────────────────
_pages = [
    st.Page("pages/project.py", title="Project",  icon="📋"),
    st.Page("pages/siteiq.py",  title="SiteIQ",   icon="🌍"),
    st.Page("pages/topoiq.py",  title="TopoIQ",   icon="⛰️"),
    st.Page("pages/yieldiq.py", title="YieldIQ",  icon="⚡"),
]
_ADMIN = {"ismailpasha747@gmail.com"}
_user_email = st.session_state.get("pvm_email", "").lower().strip()
if _user_email in _ADMIN:
    _pages.append(st.Page("pages/_layoutiq.py", title="LayoutIQ", icon="📐"))

pg = st.navigation(_pages, position="hidden")

# ── Auth gate ─────────────────────────────────────────────────────────────────
if not render_auth_page("PVMath"):
    st.stop()

# ── Restore project context if session was cleared (back button / refresh) ────
_uid_for_load = st.session_state.get("pvm_user_id", "")
if _uid_for_load and "pvm_project" not in st.session_state:
    _loaded = load_project(_uid_for_load)
    if _loaded:
        st.session_state["pvm_project"] = _loaded

# ── Restore sidebar after auth (auth page collapses it to width:0)
st.markdown("""
<style>
section[data-testid="stSidebar"] {
    width: var(--sidebar-width, 21rem) !important;
    min-width: 14rem !important;
    overflow: visible !important;
}
[data-testid="collapsedControl"] { display: flex !important; }
</style>
""", unsafe_allow_html=True)

# ── Sidebar (full control — logo + logout at top, nav links below) ────────────
_proj      = st.session_state.get("pvm_project", {})
_proj_mode = _proj.get("mode", "")
_topo_ok   = _proj_mode == "full" and bool(_proj.get("polygon_coords"))

with st.sidebar:
    email = st.session_state.get("pvm_email", "")
    st.markdown(f"""
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&display=swap" rel="stylesheet">
    <style>
      section[data-testid="stSidebar"] {{
        background: #f0f4f0 !important;
        font-family: 'Inter', sans-serif !important;
      }}
      section[data-testid="stSidebar"] * {{
        font-family: 'Inter', sans-serif !important;
      }}
      [data-testid="stSidebarNavLink"] span {{
        font-weight: 600 !important;
        font-size: 0.95rem !important;
      }}
    </style>
    <div style="padding:0.6rem 0 0.8rem 0;border-bottom:1px solid #d4e4d4;margin-bottom:0.8rem;">
      <div style="display:flex;align-items:center;gap:0.6rem;margin-bottom:0.6rem;">
        <svg width="34" height="34" viewBox="0 0 46 46" xmlns="http://www.w3.org/2000/svg">
          <rect width="46" height="46" rx="10" fill="#145f34"/>
          <path d="M0 10 Q0 0 10 0 H36 Q46 0 46 10 V14 H0 Z" fill="#1d9e52"/>
          <text x="23" y="31" text-anchor="middle" dominant-baseline="middle"
                font-family="Arial Black,Arial,sans-serif" font-size="18" font-weight="900" fill="white">PV</text>
        </svg>
        <div>
          <div style="font-weight:800;font-size:1rem;color:#0d1a0d;letter-spacing:-0.02em;line-height:1.1;">PVMath</div>
          <div style="font-size:0.65rem;color:#4a7a4a;font-weight:600;letter-spacing:0.03em;">SOLAR SITE INTELLIGENCE</div>
        </div>
      </div>
      <div style="font-size:0.72rem;color:#3a5a3a;padding:0.3rem 0.5rem;
                  background:#e8f0e8;border-radius:6px;line-height:1.4;">
        <span style="opacity:0.7;">Logged in as</span><br>
        <strong style="color:#0d1a0d;word-break:break-all;">{email}</strong>
      </div>
    </div>
    """, unsafe_allow_html=True)

    if st.button("Log out", key="sidebar_logout", use_container_width=True):
        sign_out()
        st.rerun()

    st.markdown("""
    <div style="margin-top:1.2rem;margin-bottom:0.4rem;">
      <div style="font-size:0.62rem;font-weight:800;text-transform:uppercase;
                  letter-spacing:0.12em;color:#1d9e52;">Modules</div>
    </div>
    """, unsafe_allow_html=True)

    st.page_link("pages/project.py",  label="Project",  icon="📋")
    st.page_link("pages/siteiq.py",   label="SiteIQ",   icon="🌍")

    # TopoIQ — greyed out unless project is in Full Mode with a drawn boundary
    st.page_link("pages/topoiq.py",   label="TopoIQ",   icon="⛰️", disabled=not _topo_ok)
    if not _topo_ok:
        _reason = "Select Full Mode and draw a site boundary in Project to unlock."
        st.markdown(
            f'<div style="font-size:0.74rem;color:#8a6a2a;background:#fff8e8;'
            f'border:1px solid #e8d8a0;border-radius:6px;padding:0.3rem 0.6rem;'
            f'margin:-0.3rem 0 0.6rem 1.8rem;line-height:1.4;">⛰️ TopoIQ requires '
            f'<strong>Full Mode</strong> with a drawn boundary.<br>'
            f'<span style="opacity:0.8;">{_reason}</span></div>',
            unsafe_allow_html=True,
        )

    st.page_link("pages/yieldiq.py",  label="YieldIQ",  icon="⚡")
    if _user_email in _ADMIN:
        st.page_link("pages/_layoutiq.py", label="LayoutIQ", icon="📐")

pg.run()
