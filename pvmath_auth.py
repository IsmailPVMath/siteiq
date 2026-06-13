"""
PVMath — Supabase Auth + Usage Tracker
---------------------------------------
Handles user registration, login, email confirmation,
and per-user per-module usage tracking.

Requires environment variables (set in Streamlit Cloud secrets):
  SUPABASE_URL  = https://xxxx.supabase.co
  SUPABASE_KEY  = your anon/public key
"""

import os
import streamlit as st
from supabase import create_client, Client

# ── Config ────────────────────────────────────────────────────
FREE_LIMIT   = 5
STRIPE_LINK  = "https://buy.stripe.com/YOUR_LINK_HERE"
PRICE_LABEL  = "€99 / month"

# ── Supabase client (cached) ──────────────────────────────────
@st.cache_resource
def get_supabase() -> Client:
    # Try os.environ first (Railway), fall back to st.secrets (Streamlit Cloud)
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_KEY", "")
    if not url or not key:
        try:
            url = url or st.secrets["SUPABASE_URL"]
            key = key or st.secrets["SUPABASE_KEY"]
        except Exception:
            pass
    if not url or not key:
        st.error("⚠️ Supabase credentials missing.")
        st.stop()
    return create_client(url, key)


# ── Auth functions ────────────────────────────────────────────
def sign_up(email: str, password: str) -> dict:
    try:
        sb = get_supabase()
        res = sb.auth.sign_up({"email": email, "password": password})
        return {"success": True, "user": res.user}
    except Exception as e:
        return {"success": False, "error": str(e)}


def sign_in(email: str, password: str) -> dict:
    try:
        sb = get_supabase()
        res = sb.auth.sign_in_with_password({"email": email, "password": password})
        return {"success": True, "user": res.user, "session": res.session}
    except Exception as e:
        msg = str(e)
        if "Email not confirmed" in msg:
            return {"success": False, "error": "email_not_confirmed"}
        return {"success": False, "error": msg}


def sign_out():
    try:
        get_supabase().auth.sign_out()
    except Exception:
        pass
    for key in ["pvm_user", "pvm_user_id", "pvm_email"]:
        st.session_state.pop(key, None)


# ── Admin check ───────────────────────────────────────────────
def is_admin(user_id: str) -> bool:
    """Returns True if the user has the admin flag set in profiles."""
    try:
        sb = get_supabase()
        res = sb.table("profiles").select("is_admin").eq("id", user_id).execute()
        return res.data[0]["is_admin"] if res.data else False
    except Exception:
        return False


# ── Usage tracking ────────────────────────────────────────────
def get_usage(user_id: str, app: str) -> int:
    try:
        sb = get_supabase()
        res = sb.table("usage_tracking").select("count").eq("user_id", user_id).eq("app", app).execute()
        return res.data[0]["count"] if res.data else 0
    except Exception:
        return 0


def increment_usage(user_id: str, app: str) -> int:
    """Increments usage counter. Admins are tracked but never blocked."""
    try:
        sb = get_supabase()
        current = get_usage(user_id, app)
        new_count = current + 1
        if current == 0:
            sb.table("usage_tracking").insert({"user_id": user_id, "app": app, "count": 1}).execute()
        else:
            sb.table("usage_tracking").update({"count": new_count}).eq("user_id", user_id).eq("app", app).execute()
        return new_count
    except Exception:
        return 0


def is_over_limit(user_id: str, app: str) -> bool:
    """Admins are never over the limit."""
    if is_admin(user_id):
        return False
    return get_usage(user_id, app) >= FREE_LIMIT


def remaining(user_id: str, app: str) -> int:
    """Admins see unlimited (999) remaining."""
    if is_admin(user_id):
        return 999
    return max(0, FREE_LIMIT - get_usage(user_id, app))


# ── Auth UI ───────────────────────────────────────────────────
def render_auth_page(app_name: str = "PVMath"):
    """
    Renders a full-page login / register UI.
    Returns True if user is authenticated, False otherwise.
    Call at the top of each Streamlit app.
    """

    # Already logged in?
    if st.session_state.get("pvm_user_id"):
        return True

    # ── Styles ────────────────────────────────────────────────
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif !important;
        background-color: #f5f7f5 !important;
        color: #1a2e1a !important;
    }
    [data-testid="stAppViewContainer"],
    [data-testid="stMain"],
    [data-testid="stMainBlockContainer"],
    .main, .stApp {
        background-color: #f5f7f5 !important;
    }

    /* Hide ALL Streamlit branding — no exceptions */
    #MainMenu { visibility: hidden !important; }
    footer { visibility: hidden !important; height: 0 !important; }
    header { visibility: hidden !important; }
    [data-testid="stToolbar"]       { display: none !important; }
    [data-testid="stDeployButton"]  { display: none !important; }
    [data-testid="stStatusWidget"]  { display: none !important; }
    [data-testid="stDecoration"]    { display: none !important; }
    #stDecoration                   { display: none !important; }
    [class*="viewerBadge"]          { display: none !important; }
    [class*="StatusWidget"]         { display: none !important; }
    [class*="deployButton"]         { display: none !important; }
    [class*="styles_viewerBadge"]   { display: none !important; }
    iframe[title="streamlitApp"]    { display: none !important; }
    div[data-stale="false"] > div > div > div:last-child > div[class*="badge"] { display: none !important; }

    /* Nuke bottom-right fixed/absolute Streamlit badges by position */
    [style*="position: fixed"][style*="bottom"][style*="right"],
    [style*="position:fixed"][style*="bottom"][style*="right"] {
        display: none !important;
    }


    /* Full page centering */
    .block-container {
        padding-top: 0 !important;
        max-width: 100% !important;
    }

    /* Logo sub */
    .auth-logo-sub {
        font-size: 0.8rem; color: #5a7a5a; text-align: center;
        margin-bottom: 2rem; font-weight: 500; letter-spacing: 0.04em;
    }

    /* Auth title & sub */
    .auth-title {
        font-size: 1.1rem; font-weight: 800; color: #1a2e1a;
        letter-spacing: -0.02em; margin-bottom: 0.25rem;
    }
    .auth-sub {
        font-size: 0.82rem; color: #5a7a5a; margin-bottom: 1.4rem; line-height: 1.5;
    }
    .free-badge {
        background: #e8f5ee; border: 1px solid #b8ddc8;
        color: #145f34; font-size: 0.78rem; font-weight: 700;
        padding: 0.55rem 1rem; border-radius: 9px; margin-bottom: 1.4rem;
        line-height: 1.5; letter-spacing: 0.01em;
    }

    /* Buttons */
    .stButton > button {
        background: linear-gradient(135deg, #1d9e52, #145f34) !important;
        color: #fff !important; border: none !important;
        border-radius: 9px !important; font-weight: 700 !important;
        font-size: 0.92rem !important; padding: 0.72rem 1rem !important;
        width: 100% !important; transition: all .2s !important;
        letter-spacing: 0.01em !important;
        box-shadow: 0 2px 10px rgba(29,158,82,.25) !important;
    }
    .stButton > button:hover {
        box-shadow: 0 6px 20px rgba(29,158,82,.4) !important;
        transform: translateY(-1px) !important;
    }

    /* Inputs */
    .stTextInput > div > input {
        background: #ffffff !important;
        border: 1.5px solid #d4e0d4 !important; border-radius: 9px !important;
        font-family: 'Inter', sans-serif !important; font-size: 0.88rem !important;
        color: #1a2e1a !important;
    }
    .stTextInput > div > input:focus {
        border-color: #1d9e52 !important;
        box-shadow: 0 0 0 3px rgba(29,158,82,.12) !important;
        background: #ffffff !important;
    }
    .stTextInput > label { color: #5a7a5a !important; font-size: 0.82rem !important; }

    /* Tabs */
    .stTabs [data-baseweb="tab-list"] {
        gap: 0.5rem; border-bottom: 2px solid #d4e0d4;
        background: transparent !important;
    }
    .stTabs [data-baseweb="tab"] {
        font-weight: 600 !important; color: #5a7a5a !important;
        font-size: 0.88rem !important; background: transparent !important;
    }
    .stTabs [aria-selected="true"] {
        color: #145f34 !important;
        border-bottom-color: #1d9e52 !important;
    }

    /* Footer link */
    .auth-footer {
        text-align: center; margin-top: 1.5rem;
        font-size: 0.75rem; color: #5a7a5a;
    }
    .auth-footer a { color: #1d9e52; text-decoration: none; font-weight: 600; }
    </style>
    <script>
    (function() {
      function killBadge() {
        // Target any fixed bottom-right element (Streamlit badge lives here)
        document.querySelectorAll('*').forEach(function(el) {
          try {
            var s = window.getComputedStyle(el);
            var cl = el.className || '';
            var id = el.id || '';
            if (
              (s.position === 'fixed' && parseInt(s.bottom) >= 0 && parseInt(s.right) >= 0 && el.tagName !== 'BODY') ||
              cl.toString().toLowerCase().includes('badge') ||
              cl.toString().toLowerCase().includes('viewer') ||
              id.toLowerCase().includes('badge')
            ) {
              el.style.setProperty('display', 'none', 'important');
              el.style.setProperty('visibility', 'hidden', 'important');
            }
          } catch(e) {}
        });
      }
      // Run immediately and observe DOM changes
      killBadge();
      var obs = new MutationObserver(killBadge);
      obs.observe(document.body || document.documentElement, {childList: true, subtree: true});
    })();
    </script>
    """, unsafe_allow_html=True)

    # ── Logo + tagline ─────────────────────────────────────────
    st.markdown(f"""
    <div style="text-align:center;margin-top:2.5rem;margin-bottom:0.5rem;">
      <div style="display:flex;align-items:center;gap:0.7rem;justify-content:center;margin-bottom:0.4rem;">
        <svg width="46" height="46" viewBox="0 0 46 46" xmlns="http://www.w3.org/2000/svg" style="flex-shrink:0;display:block;">
          <rect width="46" height="46" rx="10" fill="#145f34"/>
          <path d="M0 10 Q0 0 10 0 H36 Q46 0 46 10 V14 H0 Z" fill="#1d9e52"/>
          <text x="23" y="32" text-anchor="middle" dominant-baseline="middle" font-family="Arial Black,Arial,sans-serif" font-size="18" font-weight="900" fill="white">PV</text>
        </svg>
        <span style="font-family:Inter,sans-serif;font-size:1.7rem;font-weight:800;color:#1a2e1a;letter-spacing:-0.04em;">PVMath</span>
      </div>
      <div class="auth-logo-sub">Solar Site Intelligence &nbsp;·&nbsp; {app_name}</div>
    </div>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 1.6, 1])
    with col2:

        tab_login, tab_register = st.tabs(["Log In", "Create Account"])

        # ── REGISTER TAB ──────────────────────────────────────
        with tab_register:
            st.markdown("""
            <div class="free-badge">
              ✦ &nbsp;5 free analyses per module — no credit card required
            </div>
            """, unsafe_allow_html=True)

            st.markdown('<div class="auth-title">Create your account</div>', unsafe_allow_html=True)
            st.markdown('<div class="auth-sub">Enter your work email to get started.</div>', unsafe_allow_html=True)

            reg_email = st.text_input("Email address", key="reg_email", placeholder="you@company.com")
            reg_pass  = st.text_input("Password", key="reg_pass", type="password", placeholder="Min. 8 characters")
            reg_pass2 = st.text_input("Confirm password", key="reg_pass2", type="password", placeholder="Repeat password")

            if st.button("Create Account →", key="btn_register"):
                if not reg_email or not reg_pass:
                    st.error("Please enter your email and password.")
                elif len(reg_pass) < 8:
                    st.error("Password must be at least 8 characters.")
                elif reg_pass != reg_pass2:
                    st.error("Passwords do not match.")
                else:
                    with st.spinner("Creating your account…"):
                        result = sign_up(reg_email, reg_pass)
                    if result["success"]:
                        st.success("✅ Account created! Check your inbox for a confirmation email. Click the link, then come back here to log in.")
                    else:
                        err = result.get("error", "")
                        if "already registered" in err.lower() or "already been registered" in err.lower():
                            st.error("This email is already registered. Please log in.")
                        else:
                            st.error(f"Registration failed: {err}")

        # ── LOGIN TAB ─────────────────────────────────────────
        with tab_login:
            st.markdown('<div class="auth-title">Welcome back</div>', unsafe_allow_html=True)
            st.markdown('<div class="auth-sub">Log in to access your PVMath tools.</div>', unsafe_allow_html=True)

            login_email = st.text_input("Email address", key="login_email", placeholder="you@company.com")
            login_pass  = st.text_input("Password", key="login_pass", type="password", placeholder="Your password")

            if st.button("Log In →", key="btn_login"):
                if not login_email or not login_pass:
                    st.error("Please enter your email and password.")
                else:
                    with st.spinner("Logging in…"):
                        result = sign_in(login_email, login_pass)
                    if result["success"]:
                        st.session_state["pvm_user_id"] = result["user"].id
                        st.session_state["pvm_email"]   = result["user"].email
                        st.rerun()
                    elif result.get("error") == "email_not_confirmed":
                        st.warning("📬 Please confirm your email first. Check your inbox for the confirmation link, then try again.")
                    else:
                        st.error("Incorrect email or password.")

        st.markdown("""
        <div class="auth-footer">
          <a href="https://pvmath.com" target="_blank">pvmath.com</a>
          &nbsp;·&nbsp; Solar Site Intelligence
          &nbsp;·&nbsp; <a href="mailto:contact@pvmath.de">contact@pvmath.de</a>
        </div>
        """, unsafe_allow_html=True)

    return False


def show_user_header(app_name: str):
    """Shows a small header bar with the logged-in user's email and a logout button."""
    email = st.session_state.get("pvm_email", "")
    col1, col2 = st.columns([5, 1])
    with col2:
        if st.button("Log out", key="btn_logout"):
            sign_out()
            st.rerun()


def show_paywall(app_label: str):
    """Renders the upgrade paywall when the free limit is reached."""
    st.markdown(f"""
    <div style="
        background: #fff; border: 1.5px solid #1d9e52; border-radius: 14px;
        padding: 2rem 2rem 1.8rem; text-align: center; margin: 2rem 0;
        box-shadow: 0 4px 24px rgba(29,158,82,.1);
    ">
      <div style="font-size:2rem;margin-bottom:0.8rem;">🔒</div>
      <div style="font-size:1.1rem;font-weight:800;color:#1a2e1a;letter-spacing:-0.02em;margin-bottom:0.5rem;">
        Free trial complete
      </div>
      <div style="font-size:0.88rem;color:#5a7a5a;line-height:1.6;margin-bottom:1.5rem;max-width:340px;margin-left:auto;margin-right:auto;">
        You've used your 5 free {app_label} analyses. Upgrade to Professional for unlimited access to all modules.
      </div>
      <a href="{STRIPE_LINK}" target="_blank" style="
          display:inline-block;
          background:linear-gradient(135deg,#1d9e52,#145f34);
          color:#fff;text-decoration:none;padding:0.8rem 2rem;
          border-radius:9px;font-weight:700;font-size:0.95rem;
          box-shadow:0 4px 16px rgba(29,158,82,.3);
      ">Upgrade — {PRICE_LABEL} →</a>
      <div style="font-size:0.75rem;color:#5a7a5a;margin-top:1rem;">
        Cancel anytime &nbsp;·&nbsp; All modules included &nbsp;·&nbsp; VAT invoice provided
      </div>
    </div>
    """, unsafe_allow_html=True)
