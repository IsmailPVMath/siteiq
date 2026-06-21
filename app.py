import html as _html
import json
import streamlit as st
import streamlit.components.v1 as components
from pvmath_auth import (
    render_auth_page, sign_out, load_latest_project,
    refresh_user_profile, update_user_name,
)
from pvmath_team import render_membership_panel, render_team_invite_banner

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
      if (!_freshToken) {
        var _cm = document.cookie.match(/(?:^|;\\s*)pvm_s=([^;]*)/);
        if (_cm) { _freshToken = decodeURIComponent(_cm[1]); }
      }
      var _lastHealed  = sessionStorage.getItem('pvm_s_healed_to') || '';
      if (_freshToken && _freshToken !== _urlToken && _freshToken !== _lastHealed) {
        sessionStorage.setItem('pvm_s_healed_to', _freshToken);
        _params.set('s', _freshToken);
        _win.location.replace(_win.location.pathname + '?' + _params.toString());
      }

      // Install these listeners only ONCE per browser tab. This whole script
      // block re-runs on every single Streamlit rerun (every button click,
      // every map click/drag) because it's a components.html() call that
      // gets freshly re-mounted each time the page script executes top to
      // bottom. Without this guard, each rerun added ANOTHER permanent
      // 'popstate'/'pageshow' listener to window.parent that was never
      // cleaned up — after a few quick reruns (e.g. clicking Save Project
      // twice in a row) dozens of these could be stacked up, each one able
      // to independently force a hard location.reload()/replace(). That's
      // what was causing an unplanned full-page reload mid-save: the user's
      // click got swallowed by a reload that was already in flight, and the
      // very next reload after a successful save dropped them on a stale
      // bfcache snapshot with no sidebar. Guarding with a flag means the
      // listeners are attached exactly once per tab, no matter how many
      // reruns happen during the session.
      if (!_win.__pvmBfListenersInstalled) {
        _win.__pvmBfListenersInstalled = true;
        _win.addEventListener('pageshow', function(event) {
          if (event.persisted) { _win.location.reload(); }
        });
        _win.addEventListener('popstate', function() {
          _win.location.reload();
        });
      }
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

# ── Server-readable session token (survives hard refresh before JS runs) ───────
# localStorage heal (components.html above) only runs in the browser AFTER the
# first server response. On a hard refresh with no ?s= in the URL, that first
# pass used to hit the auth gate with no token and bounce to login — even when
# the browser still had a valid token in localStorage. Mirroring the token into
# an HttpOnly-less cookie lets Python read it on the very first request.
try:
    _cookie_rt = (st.context.cookies.get("pvm_s") or "").strip()
except Exception:
    _cookie_rt = ""
if _cookie_rt and not st.query_params.get("s"):
    st.query_params["s"] = _cookie_rt

# ── Auth gate ─────────────────────────────────────────────────────────────────
if not render_auth_page("PVMath"):
    st.stop()

# ── Restore project context if session was cleared (back button / refresh) ────
_uid_for_load = st.session_state.get("pvm_user_id", "")
if _uid_for_load and "pvm_project" not in st.session_state and not st.session_state.get("pvm_blank_project"):
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
  [data-testid="stSidebarCollapseButton"] {{
    display: none !important;
  }}
  /* Keep Streamlit's expand control visible — our custom hide toggle lives inside
     the sidebar, so if Streamlit slides the sidebar off-canvas the native expand
     icon is the only way back without breaking the main layout with fixed CSS. */
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
    visibility: visible !important;
  }}
  section[data-testid="stSidebar"][aria-expanded="false"] {{
    width: {_sb_width} !important;
    min-width: {_sb_width} !important;
    display: block !important;
  }}
  /* Streamlit 1.46+ slides the inner wrapper off-canvas when aria-expanded=false.
     Our Python toggle can still think the sidebar is "open" while the frontend
     has it fully hidden — and we hide Streamlit's native re-expand control.
     Force every inner wrapper to stay on-canvas. */
  section[data-testid="stSidebar"] > div,
  section[data-testid="stSidebar"] [data-testid="stSidebarContent"],
  section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] {{
    margin-left: 0 !important;
    transform: none !important;
    -webkit-transform: none !important;
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

# Heal Streamlit's native collapsed state when our toggle says "open".
components.html(
    f"""
    <script>
    (function() {{
      try {{
        var _win = window.parent;
        if (!_win || !{json.dumps(bool(_sb_open))}) return;
        function _expandSidebar() {{
          var sb = _win.document.querySelector('section[data-testid="stSidebar"]');
          if (!sb || sb.getAttribute('aria-expanded') !== 'false') return;
          var btn = _win.document.querySelector('[data-testid="stSidebarCollapsedControl"]')
            || _win.document.querySelector('[data-testid="collapsedControl"]');
          if (btn) {{ btn.click(); return; }}
          sb.setAttribute('aria-expanded', 'true');
        }}
        _expandSidebar();
        setTimeout(_expandSidebar, 120);
        setTimeout(_expandSidebar, 500);
      }} catch (e) {{}}
    }})();
    </script>
    """,
    height=0,
)

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
          <div style="margin-top:0.55rem;display:inline-flex;align-items:center;gap:0.35rem;background:rgba(29,158,82,0.18);border:1px solid rgba(125,217,154,0.45);color:#b8f5c8;font-size:0.62rem;font-weight:800;letter-spacing:0.08em;text-transform:uppercase;padding:0.28rem 0.55rem;border-radius:100px;">
            <span style="width:6px;height:6px;border-radius:50%;background:#4ade80;display:inline-block;"></span>
            Early Access
          </div>
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

        # ── Project hub ───────────────────────────────────────────────────
        _sb_proj = st.session_state.get("pvm_project", {})
        _sb_proj_name = (_sb_proj.get("name") or "").strip()
        st.markdown('<div class="pvm-group-label">Project</div>', unsafe_allow_html=True)
        st.page_link("pages/project.py", label="Project Setup")
        if _sb_proj_name:
            st.markdown(
                f'<div style="font-size:0.72rem;color:#8ab88a;padding:0.1rem 0.55rem 0.35rem;'
                f'line-height:1.35;overflow-wrap:break-word;">'
                f'Active: {_html.escape(_sb_proj_name)}</div>',
                unsafe_allow_html=True,
            )

        st.markdown('<div class="pvm-group-label">Modules</div>', unsafe_allow_html=True)
        st.page_link("pages/siteiq.py", label="SiteIQ")
        st.page_link("pages/yieldiq.py", label="YieldIQ")
        st.page_link("pages/topoiq.py", label="TopoIQ")
        if _user_email in _ADMIN:
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
            if st.button("Manage membership", key="pvm_membership_toggle", use_container_width=True):
                st.session_state["pvm_show_membership"] = not st.session_state.get("pvm_show_membership", False)

            _uid = st.session_state.get("pvm_user_id", "")
            render_team_invite_banner(_uid, email)

            if st.session_state.get("pvm_show_settings"):
                refresh_user_profile()
                st.markdown(
                    f'<div style="font-size:0.8rem;color:#ffffff;line-height:1.6;'
                    f'padding:0.1rem 0.1rem 0.4rem 0.1rem;">'
                    f'Email: {email}</div>',
                    unsafe_allow_html=True,
                )
                with st.form("pvm_name_form", clear_on_submit=False):
                    _set_fn = st.text_input(
                        "Given name(s)",
                        value=st.session_state.get("pvm_first_name", ""),
                        key="pvm_settings_first",
                        placeholder="Mohammed",
                        help="Multiple words OK.",
                    )
                    _set_ln = st.text_input(
                        "Family name(s)",
                        value=st.session_state.get("pvm_last_name", ""),
                        key="pvm_settings_last",
                        placeholder="Pasha",
                        help="Multiple words OK (e.g. Van der Berg).",
                    )
                    if st.form_submit_button("Save name", use_container_width=True):
                        _res = update_user_name(_set_fn, _set_ln)
                        if _res.get("success"):
                            st.success("Name saved — reports will show this.")
                        else:
                            st.error(_res.get("error", "Could not save name."))

            if st.session_state.get("pvm_show_membership"):
                render_membership_panel(_uid, email)

            if st.button("Log out", key="sidebar_logout", use_container_width=True):
                sign_out()
                st.rerun()

pg.run()

# ── Re-assert the session token into the URL, AFTER navigation ────────────────
# Streamlit's own multipage router (st.navigation + page_link/switch_page) can
# silently strip query params from the visible browser URL on a page switch —
# this is a known Streamlit front-end behavior, not something our code does.
# Since "s" (the Supabase refresh token) is the ONLY thing that lets a hard
# refresh restore the session, losing it from the address bar after navigating
# anywhere in the app meant every subsequent refresh forced a fresh login.
#
# This USED to be done via `st.query_params["s"] = _rt`, which goes through
# Streamlit's own URL-sync. That sync appears to register a new browser
# history entry every time it fires — on top of the entry the page switch
# itself just created. So one logical in-app navigation (e.g. Project ->
# TopoIQ) silently consumed TWO history slots: pressing Back once only undid
# half of it, and the popstate listener above (which forces a reload on every
# Back/Forward) re-ran this same reassertion on that reload, pushing yet
# another entry that wiped out whatever was sitting in the Forward stack —
# explaining both "have to press Back twice" and "Forward goes grey after".
#
# Fix: write the token straight into the address bar via history.replaceState()
# instead. That still keeps the URL carrying the current token (so a hard
# refresh recovers the session exactly as before) but replaceState by
# definition only ever edits the CURRENT history entry — it can never add one,
# so it can't create the double-entry-per-navigation effect above. Combined
# here with the existing localStorage mirror (used by the self-heal script at
# the top of this file to recover a stale "s" from an old history entry).
_rt = st.session_state.get("pvm_refresh_token", "")
if _rt:
    components.html(
        f"""
        <script>
        try {{
          var _win = window.parent;
          var _params = new URLSearchParams(_win.location.search);
          if (_params.get('s') !== {json.dumps(_rt)}) {{
            _params.set('s', {json.dumps(_rt)});
            _win.history.replaceState(null, '', _win.location.pathname + '?' + _params.toString());
          }}
          _win.localStorage.setItem('pvm_s', {json.dumps(_rt)});
          _win.document.cookie = 'pvm_s=' + encodeURIComponent({json.dumps(_rt)})
            + ';path=/;max-age=2592000;SameSite=Lax';
        }} catch (e) {{}}
        </script>
        """,
        height=0,
    )
