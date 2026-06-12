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
    url = st.secrets.get("SUPABASE_URL") or os.environ.get("SUPABASE_URL", "")
    key = st.secrets.get("SUPABASE_KEY") or os.environ.get("SUPABASE_KEY", "")
    if not url or not key:
        st.error("⚠️ Supabase credentials missing. Add SUPABASE_URL and SUPABASE_KEY to your Streamlit secrets.")
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
        background-color: #f7faf8 !important;
    }

    /* Hide Streamlit chrome on auth page */
    #MainMenu { visibility: hidden; }
    footer { visibility: hidden; }
    header { visibility: hidden; }
    [data-testid="stToolbar"] { display: none; }

    /* Full page centering */
    .block-container {
        padding-top: 0 !important;
        max-width: 100% !important;
    }

    /* Auth page background */
    .auth-page-bg {
        min-height: 100vh;
        background: linear-gradient(160deg, #f0f7f2 0%, #ffffff 60%, #e8f5ee 100%);
        display: flex; align-items: center; justify-content: center;
        padding: 2rem 1rem;
    }

    /* Logo */
    .auth-logo {
        display: flex; align-items: center; gap: 0.7rem;
        justify-content: center; margin-bottom: 0.5rem;
    }
    .auth-logo-mark {
        width: 42px; height: 42px; border-radius: 10px;
        background: linear-gradient(135deg, #145f34, #1d9e52);
        display: flex; align-items: center; justify-content: center;
        color: #fff; font-weight: 800; font-size: 1.2rem;
        box-shadow: 0 4px 12px rgba(29,158,82,.3);
    }
    .auth-logo-text {
        font-size: 1.6rem; font-weight: 800; color: #1a2e1a;
        letter-spacing: -0.04em;
    }
    .auth-logo-sub {
        font-size: 0.8rem; color: #5a7a5a; text-align: center;
        margin-bottom: 2rem; font-weight: 500; letter-spacing: 0.02em;
    }

    /* Card */
    .auth-card {
        background: #fff; border: 1.5px solid #d4e8d8; border-radius: 16px;
        padding: 2rem 2rem 1.8rem;
        box-shadow: 0 8px 40px rgba(29,158,82,.08), 0 2px 8px rgba(0,0,0,.04);
    }
    .auth-title {
        font-size: 1.1rem; font-weight: 800; color: #1a2e1a;
        letter-spacing: -0.02em; margin-bottom: 0.25rem;
    }
    .auth-sub {
        font-size: 0.82rem; color: #5a7a5a; margin-bottom: 1.4rem; line-height: 1.5;
    }
    .free-badge {
        background: #e8f5ee; border: 1px solid rgba(29,158,82,.3);
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
        box-shadow: 0 2px 8px rgba(29,158,82,.2) !important;
    }
    .stButton > button:hover {
        box-shadow: 0 6px 20px rgba(29,158,82,.4) !important;
        transform: translateY(-1px) !important;
    }

    /* Inputs */
    .stTextInput > div > input {
        background: #f7faf8 !important;
        border: 1.5px solid #c8dece !important; border-radius: 9px !important;
        font-family: 'Inter', sans-serif !important; font-size: 0.88rem !important;
        color: #1a2e1a !important;
    }
    .stTextInput > div > input:focus {
        border-color: #1d9e52 !important;
        box-shadow: 0 0 0 3px rgba(29,158,82,.12) !important;
        background: #fff !important;
    }

    /* Tabs */
    .stTabs [data-baseweb="tab-list"] {
        gap: 0.5rem; border-bottom: 2px solid #e0ece4;
    }
    .stTabs [data-baseweb="tab"] {
        font-weight: 600 !important; color: #5a7a5a !important;
        font-size: 0.88rem !important;
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
    """, unsafe_allow_html=True)

    # ── Logo + tagline ─────────────────────────────────────────
    st.markdown(f"""
    <div style="text-align:center;margin-top:2.5rem;margin-bottom:0.5rem;">
      <div class="auth-logo">
        <div class="auth-logo-mark">P</div>
        <span class="auth-logo-text">PVMath</span>
      </div>
      <div class="auth-logo-sub">Solar Intelligence Platform &nbsp;·&nbsp; {app_name}</div>
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
