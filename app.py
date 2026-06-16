import streamlit as st
from pvmath_auth import render_auth_page, sign_out, load_project, STRIPE_LINK, PRICE_LABEL

st.set_page_config(
    page_title="PVMath — Solar Site Intelligence",
    page_icon="🌱",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Navigation (position="hidden" = we build sidebar manually) ────────────────
_pages = [
    st.Page("pages/project.py", title="Project"),
    st.Page("pages/siteiq.py",  title="SiteIQ"),
    st.Page("pages/topoiq.py",  title="TopoIQ"),
    st.Page("pages/yieldiq.py", title="YieldIQ"),
]
_ADMIN = {"ismailpasha747@gmail.com"}
_user_email = st.session_state.get("pvm_email", "").lower().strip()
if _user_email in _ADMIN:
    _pages.append(st.Page("pages/_layoutiq.py", title="LayoutIQ"))

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


# ── Sidebar ─────────────────────────────────────────────────────────────────
# NOTE: we drive show/hide ourselves with plain session_state + CSS width,
# instead of relying on Streamlit's own built-in collapse control. That control
# is a tiny, low-contrast icon whose position changes across Streamlit versions —
# users were losing the sidebar with no way to bring it back. Our own button is
# always rendered, always labelled, and always works the same way.
_proj      = st.session_state.get("pvm_project", {})
_proj_mode = _proj.get("mode", "")
_topo_ok   = _proj_mode == "full" and bool(_proj.get("polygon_coords"))

st.session_state.setdefault("pvm_sidebar_open", True)
_sb_open  = st.session_state["pvm_sidebar_open"]
_sb_width = "250px" if _sb_open else "60px"

st.markdown(f"""
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&display=swap" rel="stylesheet">
<style>
  section[data-testid="stSidebar"] {{
    background: #0d1a0d !important;
    border-right: 1px solid #1d3a1d !important;
    width: {_sb_width} !important;
    min-width: {_sb_width} !important;
    transition: width 0.15s ease;
  }}
  /* Apply our font everywhere in the sidebar EXCEPT icon-font glyphs — forcing a
     custom font onto an icon ligature is what breaks Streamlit's built-in icons
     (they render as raw text like "expand_more" instead of the glyph). */
  section[data-testid="stSidebar"] *:not([class*="material"]):not([data-testid*="Icon"]) {{
    font-family: 'Inter', sans-serif !important;
  }}
  /* We replace Streamlit's native collapse controls with our own — hide them so
     they can't be triggered and leave the sidebar stuck. */
  [data-testid="stSidebarCollapseButton"],
  [data-testid="stSidebarCollapsedControl"],
  [data-testid="collapsedControl"] {{
    display: none !important;
  }}
  section[data-testid="stSidebar"] div[data-testid="stVerticalBlock"] {{
    height: 100%;
  }}
  section[data-testid="stSidebar"] div[data-testid="stVerticalBlockBorderWrapper"]:has(div.pvm-bottom-anchor) {{
    margin-top: auto !important;
  }}
  [data-testid="stSidebarNavLink"] {{
    border-radius: 6px !important;
    color: #e6f5e6 !important;
    padding: 0.45rem 0.7rem !important;
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
  .pvm-group-label {{
    font-size: 0.66rem; font-weight: 700; text-transform: uppercase;
    letter-spacing: 0.1em; color: #7fd99a;
    margin: 1.1rem 0 0.4rem 0.1rem;
  }}
  section[data-testid="stSidebar"] .stButton > button,
  section[data-testid="stSidebar"] .stLinkButton > a {{
    background: #16241a !important;
    color: #e6f5e6 !important;
    border: 1px solid #2d4a2d !important;
    border-radius: 6px !important;
    font-size: 0.85rem !important;
    font-weight: 600 !important;
    padding: 0.4rem 0.8rem !important;
    justify-content: flex-start !important;
  }}
  section[data-testid="stSidebar"] .stButton > button:hover,
  section[data-testid="stSidebar"] .stLinkButton > a:hover {{
    background: #1d3a1d !important;
    color: #fff !important;
    border-color: #4ade80 !important;
  }}
  .pvm-toggle-row .stButton > button {{
    justify-content: center !important;
    font-weight: 700 !important;
  }}
</style>
""", unsafe_allow_html=True)

with st.sidebar:
    email = st.session_state.get("pvm_email", "")

    if not _sb_open:
        # ── Collapsed rail: brand mark + a single, always-visible control to bring it back ──
        st.markdown("""
        <div style="display:flex;justify-content:center;padding:0.8rem 0;">
          <svg width="30" height="30" viewBox="0 0 46 46" xmlns="http://www.w3.org/2000/svg">
            <rect width="46" height="46" rx="10" fill="#145f34"/>
            <path d="M0 10 Q0 0 10 0 H36 Q46 0 46 10 V14 H0 Z" fill="#1d9e52"/>
            <text x="23" y="31" text-anchor="middle" dominant-baseline="middle"
                  font-family="Arial Black,Arial,sans-serif" font-size="16" font-weight="900" fill="white">PV</text>
          </svg>
        </div>
        """, unsafe_allow_html=True)
        st.markdown('<div class="pvm-toggle-row">', unsafe_allow_html=True)
        if st.button("›", key="pvm_sb_show", use_container_width=True, help="Show sidebar"):
            st.session_state["pvm_sidebar_open"] = True
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

    else:
        # ── Brand header ──────────────────────────────────────────────────
        st.markdown("""
        <div style="padding:0.8rem 0 0.9rem 0;border-bottom:1px solid #1d3a1d;margin-bottom:0.4rem;">
          <div style="display:flex;align-items:center;gap:0.6rem;">
            <svg width="34" height="34" viewBox="0 0 46 46" xmlns="http://www.w3.org/2000/svg">
              <rect width="46" height="46" rx="10" fill="#145f34"/>
              <path d="M0 10 Q0 0 10 0 H36 Q46 0 46 10 V14 H0 Z" fill="#1d9e52"/>
              <text x="23" y="31" text-anchor="middle" dominant-baseline="middle"
                    font-family="Arial Black,Arial,sans-serif" font-size="18" font-weight="900" fill="white">PV</text>
            </svg>
            <div>
              <div style="font-weight:800;font-size:1rem;color:#ffffff;letter-spacing:-0.02em;line-height:1.1;">PVMath</div>
              <div style="font-size:0.63rem;color:#7fd99a;font-weight:700;letter-spacing:0.06em;">SOLAR SITE INTELLIGENCE</div>
            </div>
          </div>
        </div>
        """, unsafe_allow_html=True)

        if st.button("‹  Hide sidebar", key="pvm_sb_hide", use_container_width=True):
            st.session_state["pvm_sidebar_open"] = False
            st.rerun()

        # ── Top nav group: Overview ──────────────────────────────────────
        st.markdown('<div class="pvm-group-label">Overview</div>', unsafe_allow_html=True)
        st.page_link("pages/project.py", label="Overview")

        # ── Modules group ────────────────────────────────────────────────
        st.markdown('<div class="pvm-group-label">Modules</div>', unsafe_allow_html=True)
        st.page_link("pages/siteiq.py",  label="SiteIQ")
        # TopoIQ — greyed out unless project is in Full Mode with a drawn boundary
        st.page_link("pages/topoiq.py",  label="TopoIQ", disabled=not _topo_ok)
        st.page_link("pages/yieldiq.py", label="YieldIQ")
        if _user_email in _ADMIN:
            st.page_link("pages/_layoutiq.py", label="LayoutIQ")

        # ── Bottom-pinned group: account / settings / membership / logout ──
        with st.container():
            st.markdown('<div class="pvm-bottom-anchor"></div>', unsafe_allow_html=True)
            st.markdown(f"""
            <div style="margin-top:0.8rem;padding-top:0.8rem;border-top:1px solid #1d3a1d;">
              <div style="font-size:0.74rem;color:#bcead0;padding:0.3rem 0.6rem;
                          background:#16241a;border-radius:6px;line-height:1.4;
                          border:1px solid #2d4a2d;margin-bottom:0.5rem;">
                Signed in as<br>
                <strong style="color:#ffffff;word-break:break-all;">{email}</strong>
              </div>
            </div>
            """, unsafe_allow_html=True)

            if st.button("Settings", key="pvm_settings_toggle", use_container_width=True):
                st.session_state["pvm_show_settings"] = not st.session_state.get("pvm_show_settings", False)
            if st.session_state.get("pvm_show_settings"):
                st.caption(f"Email: {email}")
                st.caption("Additional account settings are coming soon.")

            st.link_button("Manage Membership", STRIPE_LINK, use_container_width=True,
                            help=f"Upgrade to Pro — {PRICE_LABEL}")

            if st.button("Log out", key="sidebar_logout", use_container_width=True):
                sign_out()
                st.rerun()

# ── Top-right "+ New Project" action (replaces the old redundant top-bar) ─────
st.markdown("""
<style>
div[data-testid="stButton"].pvm-newproj-btn > button {
    font-size: 0.82rem !important; font-weight: 700 !important;
    padding: 0.3rem 0.9rem !important; border-radius: 20px !important;
    border: 1px solid #1d9e52 !important;
    background: #1d9e52 !important; color: #fff !important;
    line-height: 1.4 !important; height: auto !important;
}
div[data-testid="stButton"].pvm-newproj-btn > button:hover {
    background: #168442 !important; border-color: #168442 !important;
}
</style>
""", unsafe_allow_html=True)

_tb_l, _tb_r = st.columns([8, 2])
with _tb_r:
    st.markdown('<div class="pvm-newproj-btn">', unsafe_allow_html=True)
    if st.button("+ New Project", key="topbar_new_project", use_container_width=True):
        for _k in [
            "pvm_project", "proj_mode_sel", "proj_pin_lat", "proj_pin_lon",
            "proj_map_center", "proj_map_zoom", "proj_last_search",
            "proj_polygon_draft", "proj_polygon_cleared", "proj_edit_mode",
            "map_center", "map_zoom", "map_lat", "map_lon", "last_map_search",
        ]:
            st.session_state.pop(_k, None)
        st.switch_page("pages/project.py")
    st.markdown('</div>', unsafe_allow_html=True)

pg.run()
