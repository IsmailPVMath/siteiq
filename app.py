import json
import streamlit as st
import streamlit.components.v1 as components
from pvmath_auth import render_auth_page, sign_out, load_latest_project, STRIPE_LINK

st.set_page_config(
    page_title="PVMath — Solar Site Intelligence",
    page_icon="assets/logo-192.png",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Recover from browser Back/Forward (bfcache ghost pages + stale tokens) ────
# Streamlit is a single-page app running over a websocket, and our Supabase
# refresh token rotates every time it's used: each value of "s" in the address
# bar is only valid until the NEXT rotation. Browser history snapshots a
# separate URL per page visited, so pressing Back/Forward can resurface an
# "s" that's already been rotated away server-side — the auth gate correctly
# (but unhelpfully) treats that as a dead session and bounces to login. On
# top of that, Back/Forward can also restore a frozen back-forward-cache (bf-
# cache) DOM snapshot with a dead websocket behind it, or hand the URL change
# to Streamlit's own client router for a "soft" re-render that doesn't match
# the latest server-rendered sidebar.
#
# Two fixes, both additive to the existing query-param logic below:
#   1) Keep the single freshest token in localStorage (not just in whatever
#      history entry happens to be showing) and self-heal the URL from it
#      whenever they're out of sync — so a stale history entry corrects
#      itself instead of dead-ending on login. (localStorage is kept in sync
#      at the bottom of this file, right after the token is reasserted.)
#   2) Force a real reload on bfcache restore AND on any Back/Forward
#      (`popstate`) — guaranteeing the user always lands on a fresh, fully-
#      connected run with the current sidebar, instead of a stale snapshot.
components.html(
    """
    <script>
    try {
      var _win = window.parent;

      var _params     = new URLSearchParams(_win.location.search);
      var _urlToken    = _params.get('s') || '';
      var _freshToken  = localStorage.getItem('pvm_s') || '';
      var _lastHealed  = sessionStorage.getItem('pvm_s_healed_to') || '';
      if (_freshToken && _freshToken !== _urlToken && _freshToken !== _lastHealed) {
        sessionStorage.setItem('pvm_s_healed_to', _freshToken);
        _params.set('s', _freshToken);
        _win.location.replace(_win.location.pathname + '?' + _params.toString());
      }

      _win.addEventListener('pageshow', function(event) {
        if (event.persisted) { _win.location.reload(); }
      });
      _win.addEventListener('popstate', function() {
        _win.location.reload();
      });
    } catch (e) {}
    </script>
    """,
    height=0,
)

# ── Navigation (position="hidden" = we build sidebar manually) ────────────────
_pages = [
    st.Page("pages/overview.py",     title="Overview"),
    st.Page("pages/project.py",      title="Project"),
    st.Page("pages/my_projects.py",  title="My Projects"),
    st.Page("pages/siteiq.py",  title="SiteIQ"),
    st.Page("pages/topoiq.py",  title="TopoIQ"),
    st.Page("pages/yieldiq.py", title="YieldIQ"),
]
_ADMIN = {"ismailpasha747@gmail.com", "ismail.p@pvmath.de"}
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
    _loaded, _loaded_row_id = load_latest_project(_uid_for_load)
    if _loaded:
        st.session_state["pvm_project"] = _loaded
        st.session_state["pvm_project_row_id"] = _loaded_row_id
        st.session_state["pvm_saved_snapshot"] = dict(_loaded)


# ── Sidebar ─────────────────────────────────────────────────────────────────
# NOTE: we drive show/hide ourselves with plain session_state + CSS width,
# instead of relying on Streamlit's own built-in collapse control. That control
# is a tiny, low-contrast icon whose position changes across Streamlit versions —
# users were losing the sidebar with no way to bring it back. Our own button is
# always rendered, always labelled, and always works the same way.
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
  /* NOTE: st.page_link() renders [data-testid="stPageLink"] in current Streamlit
     versions, NOT [data-testid="stSidebarNavLink"] (that testid belongs to the
     native auto-generated nav, which we hide via position="hidden"). Targeting
     only the old testid meant this color rule never matched — Overview / SiteIQ /
     TopoIQ / YieldIQ silently fell back to default dim/illegible link styling.
     Both selectors are kept so this keeps working if Streamlit changes again. */
  [data-testid="stPageLink"],
  [data-testid="stSidebarNavLink"] {{
    border-radius: 6px !important;
    padding: 0.45rem 0.7rem !important;
    margin-bottom: 2px !important;
    transition: background 0.15s !important;
  }}
  [data-testid="stPageLink"] *,
  [data-testid="stSidebarNavLink"] * {{
    color: #e6f5e6 !important;
    font-weight: 600 !important;
    font-size: 0.92rem !important;
  }}
  [data-testid="stPageLink"]:hover,
  [data-testid="stSidebarNavLink"]:hover {{
    background: #1d3a1d !important;
  }}
  [data-testid="stPageLink"]:hover *,
  [data-testid="stSidebarNavLink"]:hover * {{
    color: #fff !important;
  }}
  [data-testid="stPageLink"][aria-current="page"],
  [data-testid="stSidebarNavLink"][aria-current="page"] {{
    background: #1d9e52 !important;
  }}
  [data-testid="stPageLink"][aria-current="page"] *,
  [data-testid="stSidebarNavLink"][aria-current="page"] * {{
    color: #fff !important;
  }}
  /* Disabled module links (e.g. TopoIQ before a boundary exists) — visibly
     muted, but still readable, instead of disappearing into the background. */
  [data-testid="stPageLink"][aria-disabled="true"] *,
  [data-testid="stPageLink"]:has([disabled]) * {{
    color: #6fa085 !important;
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
    font-size: 0.78rem !important;
    font-weight: 600 !important;
    padding: 0.28rem 0.7rem !important;
    min-height: 0 !important;
    height: auto !important;
    line-height: 1.3 !important;
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
  /* Show/Hide sidebar control — made as visually prominent (solid white) as
     "Manage Membership" so it can never be mistaken for missing/invisible. */
  div[data-testid="stVerticalBlock"]:has(div.pvm-sb-toggle) div[data-testid="stButton"] > button {{
    background: #ffffff !important;
    color: #145f34 !important;
    border: 1px solid #ffffff !important;
    font-weight: 700 !important;
  }}
  div[data-testid="stVerticalBlock"]:has(div.pvm-sb-toggle) div[data-testid="stButton"] > button:hover {{
    background: #eafaf0 !important;
    color: #145f34 !important;
  }}
  /* Cross-browser fix: Streamlit has its OWN native responsive auto-collapse
     for narrow viewports, completely separate from our pvm_sidebar_open
     toggle above. On some browsers (different default window size, browser
     chrome eating horizontal space, zoom/DPI) that native mechanism fires and
     slides/hides the ENTIRE sidebar off-canvas — taking our own custom toggle
     button down with it, since it lives inside the same <section>. The only
     way back was Streamlit's native re-expand control, which we deliberately
     hid above — leaving no escape hatch in those browsers. Force the sidebar
     to always stay on-canvas regardless of whatever internal state/attribute
     Streamlit uses to mark it "collapsed", so our own toggle is always
     reachable. A second, independent fail-safe button is also rendered in
     the main content area (outside the sidebar entirely) below.*/
  section[data-testid="stSidebar"] {{
    transform: none !important;
    -webkit-transform: none !important;
    margin-left: 0 !important;
    left: 0 !important;
    visibility: visible !important;
    position: relative !important;
  }}
  section[data-testid="stSidebar"][aria-expanded="false"] {{
    width: {_sb_width} !important;
    min-width: {_sb_width} !important;
    display: block !important;
  }}
  /* Fail-safe "Show sidebar" button rendered in the MAIN content area —
     reachable even if the sidebar's own DOM subtree is fully hidden/off-canvas. */
  div[data-testid="stVerticalBlock"]:has(div.pvm-mainshow-anchor) div[data-testid="stButton"] > button {{
    background: #145f34 !important;
    color: #ffffff !important;
    border: 1px solid #145f34 !important;
    font-weight: 700 !important;
    font-size: 0.82rem !important;
  }}
  /* Belt-and-suspenders for the "Signed in as" box — a prior inline-style
     !important fix was reported as still unreadable live. Re-declaring the
     same colors via a real stylesheet rule (higher in the cascade than
     nothing, and immune to any markdown-sanitizer quirk that might strip an
     inline style attribute) guarantees white text on the dark card even if
     the inline styles on the <span>/<strong> below ever get dropped. */
  .pvm-signedin-box, .pvm-signedin-box * {{
    color: #ffffff !important;
    opacity: 1 !important;
  }}
</style>
""", unsafe_allow_html=True)

if not _sb_open:
    st.markdown('<div class="pvm-mainshow-anchor"></div>', unsafe_allow_html=True)
    if st.button("☰  Show sidebar", key="pvm_mainshow_sidebar"):
        st.session_state["pvm_sidebar_open"] = True
        st.rerun()

with st.sidebar:
    email = st.session_state.get("pvm_email", "")

    if not _sb_open:
        # ── Collapsed rail: brand mark + a single, always-visible control to bring it back ──
        st.markdown("""
        <div style="display:flex;justify-content:center;padding:0.8rem 0;">
          <a href="https://pvmath.com" target="_blank" style="display:flex;">
            <svg width="30" height="30" viewBox="0 0 46 46" xmlns="http://www.w3.org/2000/svg">
              <rect width="46" height="46" rx="10" fill="#145f34"/>
              <path d="M0 10 Q0 0 10 0 H36 Q46 0 46 10 V14 H0 Z" fill="#1d9e52"/>
              <text x="23" y="31" text-anchor="middle" dominant-baseline="middle"
                    font-family="Arial Black,Arial,sans-serif" font-size="16" font-weight="900" fill="white">PV</text>
            </svg>
          </a>
        </div>
        """, unsafe_allow_html=True)
        with st.container():
            st.markdown('<div class="pvm-sb-toggle"></div>', unsafe_allow_html=True)
            if st.button("›", key="pvm_sb_show", use_container_width=True, help="Show sidebar"):
                st.session_state["pvm_sidebar_open"] = True
                st.rerun()

    else:
        # ── Brand header ──────────────────────────────────────────────────
        st.markdown("""
        <div style="padding:0.8rem 0 0.9rem 0;border-bottom:1px solid #1d3a1d;margin-bottom:0.4rem;">
          <a href="https://pvmath.com" target="_blank" style="display:flex;align-items:center;gap:0.6rem;text-decoration:none;">
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
          </a>
        </div>
        """, unsafe_allow_html=True)

        with st.container():
            st.markdown('<div class="pvm-sb-toggle"></div>', unsafe_allow_html=True)
            if st.button("‹  Hide sidebar", key="pvm_sb_hide", use_container_width=True):
                st.session_state["pvm_sidebar_open"] = False
                st.rerun()

        # ── Top nav group: Overview ──────────────────────────────────────
        st.markdown('<div class="pvm-group-label">Overview</div>', unsafe_allow_html=True)
        st.page_link("pages/overview.py", label="Overview")
        st.page_link("pages/my_projects.py", label="My Projects")

        # ── Modules group ────────────────────────────────────────────────
        # SiteIQ / TopoIQ / YieldIQ are intentionally NOT linked here anymore.
        # Each module reads its site/boundary from st.session_state["pvm_project"],
        # which is only committed once the user clicks "Save Project" on the
        # Project page — the per-project "🌍 SiteIQ / ⚡ YieldIQ / ⛰️ TopoIQ"
        # buttons rendered there (pages/project.py) only appear AFTER that save,
        # so they always carry a fully-committed project across. A sidebar link
        # could be clicked at any time, including right after drawing a boundary
        # but before saving — Streamlit then navigates away before that draft is
        # ever written to pvm_project, so the destination module finds no
        # boundary and falls back to a blank "draw your own" state. That looked
        # like a broken/old page to users who'd just drawn one. Removing the
        # sidebar shortcuts and keeping a single, always-correct entry point
        # (Project page -> Save -> module button) fixes that for good.
        if _user_email in _ADMIN:
            st.markdown('<div class="pvm-group-label">Modules</div>', unsafe_allow_html=True)
            st.page_link("pages/_layoutiq.py", label="LayoutIQ")

        # ── Bottom-pinned group: account / settings / membership / logout ──
        with st.container():
            st.markdown('<div class="pvm-bottom-anchor"></div>', unsafe_allow_html=True)
            st.markdown(f"""
            <div style="margin-top:0.8rem;padding-top:0.8rem;border-top:1px solid #1d3a1d;">
              <div class="pvm-signedin-box" style="font-size:0.78rem;color:#ffffff;padding:0.4rem 0.6rem;
                          background:#16241a;border-radius:6px;line-height:1.45;
                          border:1px solid #4ade80;margin-bottom:0.5rem;
                          overflow-wrap:break-word;word-break:normal;">
                <span style="color:#ffffff;font-size:0.78rem;font-weight:600;">Signed in as</span><br>
                <span style="color:#ffffff;font-size:0.78rem;font-weight:600;overflow-wrap:break-word;">{email}</span>
              </div>
            </div>
            """, unsafe_allow_html=True)

            if st.button("Settings", key="pvm_settings_toggle", use_container_width=True):
                st.session_state["pvm_show_settings"] = not st.session_state.get("pvm_show_settings", False)
            if st.session_state.get("pvm_show_settings"):
                # Plain white text to match the rest of the sidebar — st.caption()
                # renders in Streamlit's default muted grey, which looked
                # inconsistent/illegible against the dark sidebar background.
                st.markdown(
                    f'<div style="font-size:0.8rem;color:#ffffff;line-height:1.6;'
                    f'padding:0.1rem 0.1rem 0.4rem 0.1rem;">'
                    f'Email: {email}<br>'
                    f'Additional account settings are coming soon.'
                    f'</div>',
                    unsafe_allow_html=True
                )

            # "Manage Membership" just opens STRIPE_LINK — no price is hardcoded
            # here anymore (it was stale at €49 and the popover tooltip overlapped
            # surrounding sidebar content on touch/focus, looking broken). Once
            # STRIPE_LINK points to a real Stripe Customer Portal session, Stripe
            # itself will show the user's current plan and the correct upgrade
            # path (e.g. Pro -> Developer) — that should live in Stripe's config,
            # not be duplicated/hardcoded in the app.
            st.link_button("Manage Membership", STRIPE_LINK, use_container_width=True)

            if st.button("Log out", key="sidebar_logout", use_container_width=True):
                sign_out()
                st.rerun()

# ── Top-right "+ New Project" action (replaces the old redundant top-bar) ─────
# NOTE: styling must be anchored with a marker INSIDE the same container as the
# button (via :has()) — a <div> opened in one st.markdown call and closed in a
# later one never actually wraps the button (each st.markdown call is its own
# isolated HTML fragment), so that old approach silently failed to style/scope
# anything reliably.
#
# Skipped on the Overview page only: Overview renders its own "+ New Project"
# button inline (alongside "View My Projects" / "Continue last project"), so
# this top-bar copy was a second, redundant button stacked on top of it. Every
# other page still gets this one — it's their only "+ New Project" entry point.
if pg.title != "Overview":
    st.markdown("""
    <style>
    div[data-testid="stVerticalBlock"]:has(div.pvm-newproj-anchor) div[data-testid="stButton"] > button {
        font-size: 0.82rem !important; font-weight: 700 !important;
        padding: 0.3rem 0.9rem !important; border-radius: 20px !important;
        border: 1px solid #1d9e52 !important;
        background: #1d9e52 !important; color: #fff !important;
        line-height: 1.4 !important; height: auto !important;
    }
    div[data-testid="stVerticalBlock"]:has(div.pvm-newproj-anchor) div[data-testid="stButton"] > button:hover {
        background: #168442 !important; border-color: #168442 !important;
    }
    </style>
    """, unsafe_allow_html=True)

    _tb_l, _tb_r = st.columns([8, 2])
    with _tb_r:
        with st.container():
            st.markdown('<div class="pvm-newproj-anchor"></div>', unsafe_allow_html=True)
            if st.button("+ New Project", key="topbar_new_project", use_container_width=True):
                for _k in [
                    "pvm_project", "pvm_project_row_id", "pvm_saved_snapshot", "proj_mode_sel",
                    "proj_pin_lat", "proj_pin_lon",
                    "proj_map_center", "proj_map_zoom", "proj_last_search",
                    "proj_polygon_draft", "proj_polygon_cleared", "proj_edit_mode",
                    "map_center", "map_zoom", "map_lat", "map_lon", "last_map_search",
                    "siteiq_run_cache", "siteiq_project_name", "siteiq_country",
                    "siteiq_lat", "siteiq_lon", "siteiq_area_ha",
                ]:
                    st.session_state.pop(_k, None)
                st.switch_page("pages/project.py")

pg.run()

# ── Re-assert the session token into the URL, AFTER navigation ────────────────
# Streamlit's own multipage router (st.navigation + page_link/switch_page) can
# silently strip query params from the visible browser URL on a page switch —
# this is a known Streamlit front-end behavior, not something our code does.
# Since "s" (the Supabase refresh token) is the ONLY thing that lets a hard
# refresh restore the session, losing it from the address bar after navigating
# anywhere in the app meant every subsequent refresh forced a fresh login. Re-
# writing it here, as the very last thing this script does, makes sure the URL
# always carries the current token by the time the page settles — regardless
# of what page-routing did to it during this run.
_rt = st.session_state.get("pvm_refresh_token", "")
if _rt and st.query_params.get("s") != _rt:
    st.query_params["s"] = _rt

# Mirror the current token into localStorage on every run that has one — this
# is the single freshest copy the self-heal script (top of this file) reads
# from to recover a Back/Forward press that resurfaces an old, already-
# rotated "s" value from a stale history entry.
if _rt:
    components.html(
        f"""
        <script>
        try {{ window.parent.localStorage.setItem('pvm_s', {json.dumps(_rt)}); }} catch (e) {{}}
        </script>
        """,
        height=0,
    )
