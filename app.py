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
      /* ── Dark branded sidebar ── */
      section[data-testid="stSidebar"] {{
        background: #0d1a0d !important;
        font-family: 'Inter', sans-serif !important;
        border-right: 1px solid #1d3a1d !important;
      }}
      section[data-testid="stSidebar"] * {{
        font-family: 'Inter', sans-serif !important;
      }}
      /* Collapse toggle button */
      [data-testid="stSidebarCollapseButton"] {{
        background: #1a2e1a !important;
        border-radius: 0 8px 8px 0 !important;
      }}
      [data-testid="stSidebarCollapseButton"] svg {{
        color: #4ade80 !important;
        stroke: #4ade80 !important;
      }}
      /* Page links */
      [data-testid="stSidebarNavLink"] {{
        border-radius: 8px !important;
        color: #c8e6c9 !important;
        padding: 0.4rem 0.7rem !important;
        margin-bottom: 2px !important;
        transition: background 0.15s !important;
      }}
      [data-testid="stSidebarNavLink"]:hover {{
        background: #1d3a1d !important;
        color: #fff !important;
      }}
      [data-testid="stSidebarNavLink"][aria-current="page"] {{
        background: #1d9e52 !important;
        color: #fff !important;
      }}
      [data-testid="stSidebarNavLink"] span {{
        font-weight: 600 !important;
        font-size: 0.92rem !important;
        color: inherit !important;
      }}
      /* Logout button */
      section[data-testid="stSidebar"] .stButton > button {{
        background: #1a2e1a !important;
        color: #c8e6c9 !important;
        border: 1px solid #2d4a2d !important;
        border-radius: 8px !important;
        font-size: 0.82rem !important;
        font-weight: 600 !important;
        padding: 0.35rem 0.8rem !important;
      }}
      section[data-testid="stSidebar"] .stButton > button:hover {{
        background: #e53935 !important;
        color: #fff !important;
        border-color: #e53935 !important;
      }}
    </style>
    <div style="padding:0.8rem 0 0.9rem 0;border-bottom:1px solid #1d3a1d;margin-bottom:0.8rem;">
      <div style="display:flex;align-items:center;gap:0.6rem;margin-bottom:0.7rem;">
        <svg width="34" height="34" viewBox="0 0 46 46" xmlns="http://www.w3.org/2000/svg">
          <rect width="46" height="46" rx="10" fill="#145f34"/>
          <path d="M0 10 Q0 0 10 0 H36 Q46 0 46 10 V14 H0 Z" fill="#1d9e52"/>
          <text x="23" y="31" text-anchor="middle" dominant-baseline="middle"
                font-family="Arial Black,Arial,sans-serif" font-size="18" font-weight="900" fill="white">PV</text>
        </svg>
        <div>
          <div style="font-weight:800;font-size:1rem;color:#ffffff;letter-spacing:-0.02em;line-height:1.1;">PVMath</div>
          <div style="font-size:0.63rem;color:#4ade80;font-weight:700;letter-spacing:0.06em;">SOLAR SITE INTELLIGENCE</div>
        </div>
      </div>
      <div style="font-size:0.71rem;color:#a5c8a5;padding:0.3rem 0.6rem;
                  background:#1a2e1a;border-radius:6px;line-height:1.4;border:1px solid #2d4a2d;">
        <span style="opacity:0.65;">Logged in as</span><br>
        <strong style="color:#e8f5e8;word-break:break-all;">{email}</strong>
      </div>
    </div>
    """, unsafe_allow_html=True)

    if st.button("Log out", key="sidebar_logout", use_container_width=True):
        sign_out()
        st.rerun()

    st.markdown("""
    <div style="margin-top:1.2rem;margin-bottom:0.5rem;">
      <div style="font-size:0.6rem;font-weight:800;text-transform:uppercase;
                  letter-spacing:0.14em;color:#4ade80;">Modules</div>
    </div>
    """, unsafe_allow_html=True)

    st.page_link("pages/project.py",  label="Project",  icon="📋")
    st.page_link("pages/siteiq.py",   label="SiteIQ",   icon="🌍")

    # TopoIQ — greyed out unless project is in Full Mode with a drawn boundary
    st.page_link("pages/topoiq.py",   label="TopoIQ",   icon="⛰️", disabled=not _topo_ok)

    st.page_link("pages/yieldiq.py",  label="YieldIQ",  icon="⚡")
    if _user_email in _ADMIN:
        st.page_link("pages/_layoutiq.py", label="LayoutIQ", icon="📐")

# ── Top-bar: account chip + sign-out (always visible even if sidebar collapsed) ──
_tb_email = st.session_state.get("pvm_email", "")
if _tb_email:
    st.markdown("""
    <style>
    .pvm-topbar {
        display: flex; justify-content: flex-end; align-items: center;
        gap: 0.6rem; padding: 0.3rem 0 0.5rem 0; margin-bottom: 0.2rem;
    }
    .pvm-topbar-email {
        font-size: 0.78rem; font-weight: 600; color: #4a6a4a;
        background: #f0faf5; border: 1px solid #b2dfca;
        border-radius: 20px; padding: 0.22rem 0.75rem;
        white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
        max-width: 220px;
    }
    /* Style the sign-out button inline with the chip */
    div[data-testid="stButton"].pvm-signout-btn > button {
        font-size: 0.78rem !important; font-weight: 600 !important;
        padding: 0.2rem 0.75rem !important; border-radius: 20px !important;
        border: 1px solid #e0d0c0 !important;
        background: #fff8f5 !important; color: #8a4a2a !important;
        line-height: 1.4 !important; height: auto !important;
    }
    div[data-testid="stButton"].pvm-signout-btn > button:hover {
        background: #e53935 !important; color: #fff !important;
        border-color: #e53935 !important;
    }
    </style>
    """, unsafe_allow_html=True)

    _tb_l, _tb_r = st.columns([7, 3])
    with _tb_r:
        _chip_col, _btn_col = st.columns([3, 2])
        with _chip_col:
            st.markdown(f'<div class="pvm-topbar-email">👤 {_tb_email}</div>',
                        unsafe_allow_html=True)
        with _btn_col:
            st.markdown('<div class="pvm-signout-btn">', unsafe_allow_html=True)
            if st.button("Sign out", key="topbar_signout"):
                sign_out()
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)

pg.run()
