import streamlit as st
from pvmath_auth import render_auth_page, sign_out

st.set_page_config(
    page_title="PVMath — Solar Site Intelligence",
    page_icon="🌱",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Auth gate ─────────────────────────────────────────────────────────────────
if not render_auth_page("PVMath"):
    st.stop()

# ── Sidebar ───────────────────────────────────────────────────────────────────
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
      div[data-testid="stButton"] > button {{
        font-family: 'Inter', sans-serif !important;
        font-weight: 600 !important;
        border-radius: 8px !important;
      }}
    </style>
    <div style="padding:0.8rem 0 1rem 0;border-bottom:1px solid #d4e4d4;margin-bottom:0.8rem;">
      <div style="display:flex;align-items:center;gap:0.6rem;margin-bottom:0.5rem;">
        <svg width="36" height="36" viewBox="0 0 46 46" xmlns="http://www.w3.org/2000/svg">
          <rect width="46" height="46" rx="10" fill="#145f34"/>
          <path d="M0 10 Q0 0 10 0 H36 Q46 0 46 10 V14 H0 Z" fill="#1d9e52"/>
          <text x="23" y="31" text-anchor="middle" dominant-baseline="middle"
                font-family="Arial Black,Arial,sans-serif" font-size="18" font-weight="900" fill="white">PV</text>
        </svg>
        <div>
          <div style="font-weight:800;font-size:1.05rem;color:#1a2e1a;letter-spacing:-0.02em;line-height:1.1;">PVMath</div>
          <div style="font-size:0.7rem;color:#6a8a6a;font-weight:500;letter-spacing:0.03em;">SOLAR SITE INTELLIGENCE</div>
        </div>
      </div>
      <div style="font-size:0.75rem;color:#5a7a5a;overflow:hidden;text-overflow:ellipsis;
                  white-space:nowrap;padding:0.3rem 0.5rem;background:#e8f0e8;
                  border-radius:6px;">
        <span style="opacity:0.7;">Logged in as</span><br>
        <strong>{email}</strong>
      </div>
    </div>
    """, unsafe_allow_html=True)

    if st.button("Log out", key="sidebar_logout", use_container_width=True):
        sign_out()
        st.rerun()

    st.markdown("""
    <div style="margin-top:1.5rem;padding-top:0.8rem;border-top:1px solid #d4e4d4;">
      <div style="font-size:0.65rem;font-weight:700;text-transform:uppercase;
                  letter-spacing:0.1em;color:#8a9a8a;margin-bottom:0.6rem;">Modules</div>
    </div>
    """, unsafe_allow_html=True)

# ── Navigation ────────────────────────────────────────────────────────────────
_pages = [
    st.Page("pages/siteiq.py",  title="SiteIQ",  icon="🌍"),
    st.Page("pages/topoiq.py",  title="TopoIQ",  icon="⛰️"),
]
# YieldIQ + LayoutIQ — admin only, hidden from all other users
_ADMIN = {"ismailpasha747@gmail.com"}
_user_email = st.session_state.get("pvm_email", "").lower().strip()
if _user_email in _ADMIN:
    _pages.append(st.Page("pages/yieldiq.py",  title="YieldIQ",  icon="⚡"))
    _pages.append(st.Page("pages/layoutiq.py", title="LayoutIQ", icon="📐"))

pg = st.navigation(_pages)
pg.run()
