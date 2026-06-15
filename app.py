import streamlit as st
from pvmath_auth import render_auth_page, sign_out

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

# ── Un-hide sidebar (auth page CSS may have hidden it) ───────────────────────
st.markdown("""
<style>
section[data-testid="stSidebar"] { display: flex !important; }
[data-testid="collapsedControl"]  { display: flex !important; }
</style>
""", unsafe_allow_html=True)

# ── Sidebar (full control — logo + logout at top, nav links below) ────────────
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

    # Manual nav links — full control over position
    st.page_link("pages/project.py",  label="Project",  icon="📋")
    st.page_link("pages/siteiq.py",   label="SiteIQ",   icon="🌍")
    st.page_link("pages/topoiq.py",   label="TopoIQ",   icon="⛰️")
    st.page_link("pages/yieldiq.py",  label="YieldIQ",  icon="⚡")
    if _user_email in _ADMIN:
        st.page_link("pages/_layoutiq.py", label="LayoutIQ", icon="📐")

pg.run()
