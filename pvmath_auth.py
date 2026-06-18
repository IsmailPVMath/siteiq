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
import smtplib
import secrets
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional

import requests as _req
import streamlit as st

# ── Config ────────────────────────────────────────────────────
# Per-module monthly analysis caps, by plan. None = unlimited.
# Mirrors the live pricing page (pvmath.com) — keep these in sync if pricing changes.
PLAN_LIMITS = {
    "free":         5,
    "professional": 50,
    "developer":    250,
    "enterprise":   None,
}
DEFAULT_PLAN = "free"
FREE_LIMIT   = PLAN_LIMITS["free"]   # kept for backward compat — pages/*.py import this directly

# Team seat caps, by plan. Usage is pooled across a team (see get_team_id/_usage_key
# below) — seats control how many logins can draw on that one shared monthly pool,
# they are not an additional per-person allowance.
SEAT_LIMITS = {
    "free":         1,
    "professional": 1,
    "developer":    5,
    "enterprise":   None,
}

PLAN_LABELS = {
    "free":         "Free",
    "professional": "Professional",
    "developer":    "Developer",
    "enterprise":   "Enterprise",
}

STRIPE_LINK  = "https://buy.stripe.com/YOUR_LINK_HERE"
PRICE_LABEL  = "€49 / month"

# ── Supabase helpers (direct REST — no supabase-py) ───────────
def _sb_url() -> str:
    v = os.environ.get("SUPABASE_URL", "")
    if not v:
        try: v = st.secrets["SUPABASE_URL"]
        except Exception: pass
    if not v:
        st.error("⚠️ SUPABASE_URL missing from secrets.")
        st.stop()
    return v.rstrip("/")

def _sb_key() -> str:
    v = os.environ.get("SUPABASE_KEY", "")
    if not v:
        try: v = st.secrets["SUPABASE_KEY"]
        except Exception: pass
    if not v:
        st.error("⚠️ SUPABASE_KEY missing from secrets.")
        st.stop()
    return v

def _auth_hdr(token: str = "") -> dict:
    """Headers for /auth/v1 endpoints."""
    h = {"apikey": _sb_key(), "Content-Type": "application/json"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h

def _db_hdr() -> dict:
    """Headers for /rest/v1 DB endpoints (uses stored user token for RLS)."""
    key = _sb_key()
    token = st.session_state.get("pvm_access_token", "") or key
    return {
        "apikey": key,
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

def _parse_err(r: _req.Response) -> str:
    try:
        d = r.json()
        return d.get("msg") or d.get("message") or d.get("error_description") or d.get("error") or str(d)
    except Exception:
        return r.text or f"HTTP {r.status_code}"


# ── Auth functions (direct REST — no supabase-py) ─────────────
def sign_up(email: str, password: str) -> dict:
    try:
        r = _req.post(f"{_sb_url()}/auth/v1/signup",
                      json={"email": email, "password": password},
                      headers=_auth_hdr(), timeout=15)
        if r.status_code in (200, 201):
            data = r.json()
            # Email confirmation OFF → Supabase returns a full session object
            if data.get("access_token"):
                return {"success": True, "user": data.get("user", {}),
                        "access_token": data["access_token"],
                        "refresh_token": data.get("refresh_token", ""),
                        "auto_confirmed": True}
            # Email confirmation ON → returns user object with id at root
            if data.get("id") or data.get("user", {}).get("id"):
                return {"success": True,
                        "user": data if data.get("id") else data.get("user", {})}
        return {"success": False, "error": _parse_err(r)}
    except Exception as e:
        return {"success": False, "error": str(e)}


def sign_in(email: str, password: str) -> dict:
    try:
        r = _req.post(f"{_sb_url()}/auth/v1/token?grant_type=password",
                      json={"email": email, "password": password},
                      headers=_auth_hdr(), timeout=15)
        if r.status_code == 200:
            data = r.json()
            if data.get("access_token"):
                return {"success": True, "user": data.get("user", {}),
                        "access_token": data["access_token"],
                        "refresh_token": data.get("refresh_token", "")}
        err = _parse_err(r)
        if "not confirmed" in err.lower() or "email_not_confirmed" in err.lower():
            return {"success": False, "error": "email_not_confirmed"}
        return {"success": False, "error": err}
    except Exception as e:
        return {"success": False, "error": str(e)}


def sign_out():
    try:
        token = st.session_state.get("pvm_access_token", "")
        if token:
            _req.post(f"{_sb_url()}/auth/v1/logout",
                      headers=_auth_hdr(token), timeout=10)
    except Exception:
        pass
    # Clear the session token from URL params
    try:
        st.query_params.clear()
    except Exception:
        pass
    for key in list(st.session_state.keys()):
        del st.session_state[key]


def _refresh_session(refresh_token: str) -> dict:
    """Exchange a stored refresh token for a new Supabase session.

    Distinguishes a genuine "this token is dead" rejection from a transient
    network/timeout error reaching Supabase. The caller uses this to decide
    whether it's safe to wipe the stored token from the URL — wiping it on a
    transient hiccup permanently locks the user out on every future refresh,
    since there's nothing left to retry with.
    """
    try:
        r = _req.post(
            f"{_sb_url()}/auth/v1/token?grant_type=refresh_token",
            json={"refresh_token": refresh_token},
            headers=_auth_hdr(), timeout=15,
        )
    except Exception:
        # Couldn't even reach Supabase — not proof the token is invalid.
        return {"success": False, "retry": True}

    if r.status_code == 200:
        data = r.json()
        user = data.get("user", {})
        return {
            "success":       True,
            "user_id":       user.get("id", ""),
            "email":         user.get("email", ""),
            "access_token":  data.get("access_token", ""),
            "refresh_token": data.get("refresh_token", refresh_token),
        }
    # Supabase responded and explicitly rejected the token (expired / already
    # rotated / revoked) — this one really is dead.
    return {"success": False, "retry": False}


def resend_confirmation(email: str) -> dict:
    try:
        r = _req.post(f"{_sb_url()}/auth/v1/resend",
                      json={"type": "signup", "email": email},
                      headers=_auth_hdr(), timeout=15)
        return {"success": True} if r.status_code in (200, 204) \
               else {"success": False, "error": _parse_err(r)}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── OTP email verification ────────────────────────────────────
def _smtp_cfg():
    """Return SMTP config — checks env vars (Railway) then st.secrets (Streamlit Cloud)."""
    def _get(key, fallback=None):
        v = os.environ.get(key, "")
        if v:
            return v
        try:
            return st.secrets[key]
        except Exception:
            return fallback

    host = _get("SMTP_HOST")
    port = _get("SMTP_PORT")
    user = _get("SMTP_USER")
    pw   = _get("SMTP_PASS")
    frm  = _get("SMTP_FROM", user)

    if not all([host, port, user, pw]):
        return None

    try:
        return {"host": host, "port": int(port), "user": user, "password": pw, "from": frm}
    except Exception:
        return None


def generate_otp() -> str:
    """Return a cryptographically random 6-digit string."""
    return f"{secrets.randbelow(900000) + 100000}"


def _otp_html(otp: str) -> str:
    return f"""
<div style="font-family:Inter,Arial,sans-serif;max-width:480px;margin:0 auto;
            padding:2rem;background:#f5f7f5;border-radius:12px;">
  <div style="text-align:center;margin-bottom:1.5rem;">
    <span style="font-size:1.4rem;font-weight:800;color:#1a2e1a;">PVMath</span>
    <div style="font-size:0.8rem;color:#5a7a5a;margin-top:0.2rem;">Solar Site Intelligence</div>
  </div>
  <div style="background:#fff;border-radius:10px;padding:2rem;text-align:center;
              border:1px solid #d4e0d4;">
    <div style="font-size:0.9rem;color:#5a7a5a;margin-bottom:1.2rem;">Your verification code is:</div>
    <div style="font-size:2.4rem;font-weight:800;color:#1d9e52;letter-spacing:0.35em;
                background:#e8f5ee;padding:1rem 1.5rem;border-radius:8px;display:inline-block;">
      {otp}
    </div>
    <div style="font-size:0.8rem;color:#5a7a5a;margin-top:1.2rem;">
      Expires in <strong>10 minutes</strong>.
    </div>
  </div>
  <div style="text-align:center;margin-top:1.2rem;font-size:0.75rem;color:#888;">
    If you didn't create a PVMath account, ignore this email.
  </div>
</div>"""


def _get_env(key, fallback=None):
    v = os.environ.get(key, "")
    if v:
        return v
    try:
        return st.secrets[key]
    except Exception:
        return fallback


def send_otp_email(to_email: str, otp: str) -> dict:
    """Send OTP via Brevo HTTP API (primary) or SMTP (fallback)."""
    subject = f"PVMath — Your verification code: {otp}"
    html    = _otp_html(otp)
    plain   = (f"Your PVMath verification code is:\n\n  {otp}\n\n"
               f"Expires in 10 minutes. Do not share it.\n\n— PVMath Team\npvmath.com")

    # ── Option 1: Brevo REST API (HTTPS — works on Railway) ──────
    brevo_key = _get_env("BREVO_API_KEY")
    sender_email = _get_env("SMTP_FROM") or _get_env("SMTP_USER") or "noreply@pvmath.com"
    if brevo_key:
        try:
            r = _req.post(
                "https://api.brevo.com/v3/smtp/email",
                headers={"api-key": brevo_key, "Content-Type": "application/json"},
                json={
                    "sender":      {"name": "PVMath", "email": sender_email},
                    "to":          [{"email": to_email}],
                    "subject":     subject,
                    "htmlContent": html,
                    "textContent": plain,
                },
                timeout=15,
            )
            if r.status_code in (200, 201):
                return {"success": True}
            return {"success": False, "error": f"Brevo API error {r.status_code}: {r.text}"}
        except Exception as e:
            return {"success": False, "error": f"Brevo API exception: {e}"}

    # ── Option 2: SMTP fallback (Streamlit Cloud / local) ────────
    cfg = _smtp_cfg()
    if not cfg:
        return {"success": False, "error": "No email config: set BREVO_API_KEY (or SMTP_*) in Railway Variables."}

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = cfg["from"]
    msg["To"]      = to_email
    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(html,  "html"))

    try:
        with smtplib.SMTP(cfg["host"], cfg["port"], timeout=15) as s:
            s.ehlo()
            s.starttls()
            s.login(cfg["user"], cfg["password"])
            s.send_message(msg)
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


def reset_password_email(email: str) -> dict:
    try:
        r = _req.post(f"{_sb_url()}/auth/v1/recover",
                      json={"email": email},
                      params={"redirect_to": "https://siteiq.pvmath.com/"},
                      headers=_auth_hdr(), timeout=15)
        return {"success": True} if r.status_code in (200, 204) \
               else {"success": False, "error": _parse_err(r)}
    except Exception as e:
        return {"success": False, "error": str(e)}


def update_password(access_token: str, refresh_token: str, new_password: str) -> dict:
    try:
        r = _req.put(f"{_sb_url()}/auth/v1/user",
                     json={"password": new_password},
                     headers=_auth_hdr(access_token), timeout=15)
        return {"success": True} if r.status_code == 200 \
               else {"success": False, "error": _parse_err(r)}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Admin check ───────────────────────────────────────────────
def is_admin(user_id: str) -> bool:
    try:
        r = _req.get(f"{_sb_url()}/rest/v1/profiles",
                     params={"id": f"eq.{user_id}", "select": "is_admin"},
                     headers=_db_hdr(), timeout=10)
        data = r.json()
        return bool(data[0]["is_admin"]) if data else False
    except Exception:
        return False


# ── Plan + team helpers ─────────────────────────────────────────
def _current_period() -> str:
    """Calendar-month key, e.g. '2026-06'. Usage caps reset when this rolls over —
    no separate cron/reset job needed, the period itself is the reset mechanism."""
    return time.strftime("%Y-%m")


def get_profile(user_id: str) -> dict:
    """Raw profile row (plan, team_id, is_admin). Empty dict if not found/error."""
    try:
        r = _req.get(f"{_sb_url()}/rest/v1/profiles",
                     params={"id": f"eq.{user_id}", "select": "plan,team_id,is_admin"},
                     headers=_db_hdr(), timeout=10)
        data = r.json()
        return data[0] if data else {}
    except Exception:
        return {}


def get_plan(user_id: str) -> str:
    """The billing plan a user is on. Defaults to 'free' if unset.
    Until Stripe webhooks exist, this column is set by hand in Supabase after
    manually confirming a payment — see STRIPE_LINK above."""
    return get_profile(user_id).get("plan") or DEFAULT_PLAN


def get_team_id(user_id: str):
    """Team id if this user belongs to a pooled team account (Developer tier),
    else None for a solo account."""
    return get_profile(user_id).get("team_id") or None


def plan_limit(plan: str):
    """Per-module monthly analysis cap for a plan. None = unlimited."""
    return PLAN_LIMITS.get(plan, PLAN_LIMITS[DEFAULT_PLAN])


def seat_limit(plan: str):
    """Max team members for a plan. None = unlimited/negotiated (Enterprise)."""
    return SEAT_LIMITS.get(plan, SEAT_LIMITS[DEFAULT_PLAN])


def plan_label(plan: str) -> str:
    return PLAN_LABELS.get(plan, PLAN_LABELS[DEFAULT_PLAN])


def team_member_count(team_id: str) -> int:
    try:
        r = _req.get(f"{_sb_url()}/rest/v1/profiles",
                     params={"team_id": f"eq.{team_id}", "select": "id"},
                     headers=_db_hdr(), timeout=10)
        return len(r.json())
    except Exception:
        return 0


def can_add_seat(team_id: str, plan: str) -> bool:
    """Whether a team still has room for another member under its plan's seat cap.
    No invite UI calls this yet — it's here so a future team-invite flow has a
    ready-made check instead of re-deriving the seat math."""
    limit = seat_limit(plan)
    if limit is None:
        return True
    return team_member_count(team_id) < limit


def _usage_key(user_id: str) -> str:
    """The id usage is pooled against: a team's id for team members (so
    Developer's 5 seats share one monthly counter), else the user's own id."""
    return get_team_id(user_id) or user_id


# ── Usage tracking ────────────────────────────────────────────
# Rows are keyed by (usage_key, app, period) so counts reset naturally each
# calendar month and so team members share one counter. See
# supabase_migration_plan_limits.sql for the schema change this depends on.
def get_usage(user_id: str, app: str) -> int:
    key, period = _usage_key(user_id), _current_period()
    try:
        r = _req.get(f"{_sb_url()}/rest/v1/usage_tracking",
                     params={"usage_key": f"eq.{key}", "app": f"eq.{app}",
                              "period": f"eq.{period}", "select": "count"},
                     headers=_db_hdr(), timeout=10)
        data = r.json()
        return data[0]["count"] if data else 0
    except Exception:
        return 0


def increment_usage(user_id: str, app: str) -> int:
    key, period = _usage_key(user_id), _current_period()
    try:
        current = get_usage(user_id, app)
        new_count = current + 1
        base = f"{_sb_url()}/rest/v1/usage_tracking"
        if current == 0:
            _req.post(base, json={"user_id": user_id, "usage_key": key, "app": app,
                                   "period": period, "count": 1},
                      headers=_db_hdr(), timeout=10)
        else:
            _req.patch(base, json={"count": new_count},
                       params={"usage_key": f"eq.{key}", "app": f"eq.{app}",
                               "period": f"eq.{period}"},
                       headers=_db_hdr(), timeout=10)
        return new_count
    except Exception:
        return 0


def is_over_limit(user_id: str, app: str) -> bool:
    """Admins and Enterprise (uncapped) are never over the limit."""
    if is_admin(user_id):
        return False
    limit = plan_limit(get_plan(user_id))
    if limit is None:
        return False
    return get_usage(user_id, app) >= limit


def remaining(user_id: str, app: str) -> int:
    """Admins and Enterprise see unlimited (999) remaining."""
    if is_admin(user_id):
        return 999
    limit = plan_limit(get_plan(user_id))
    if limit is None:
        return 999
    return max(0, limit - get_usage(user_id, app))


# ── Project persistence ───────────────────────────────────────
# Each saved project is its own row in user_projects (user_id, project_data, +
# whatever id/timestamp columns Supabase already provides). save_project()
# either INSERTs a new row (row_id=None — brand new project) or PATCHes an
# existing one (row_id given — re-saving a project the user already opened),
# so a user can accumulate many projects instead of one save overwriting the
# last. This is what backs the "My Projects" dashboard.
def save_project(user_id: str, project: dict, row_id: Optional[str] = None) -> Optional[str]:
    """Insert a new project row, or update an existing one if row_id is given.
    Returns the row's id on success, or None on failure."""
    try:
        base = f"{_sb_url()}/rest/v1/user_projects"
        if row_id:
            r = _req.patch(
                base,
                json={"project_data": project},
                params={"user_id": f"eq.{user_id}", "id": f"eq.{row_id}"},
                headers={**_db_hdr(), "Prefer": "return=minimal"},
                timeout=10,
            )
            return row_id if r.status_code in (200, 204) else None
        else:
            r = _req.post(
                base,
                json={"user_id": user_id, "project_data": project},
                headers={**_db_hdr(), "Prefer": "return=representation"},
                timeout=10,
            )
            if r.status_code in (200, 201):
                rows = r.json()
                if rows and isinstance(rows, list):
                    return rows[0].get("id")
            return None
    except Exception:
        return None


def list_projects(user_id: str) -> list:
    """Return every saved project for this user, newest first (best effort —
    sorts by whichever timestamp column the table happens to have)."""
    try:
        r = _req.get(
            f"{_sb_url()}/rest/v1/user_projects",
            params={"user_id": f"eq.{user_id}", "select": "*"},
            headers=_db_hdr(), timeout=10,
        )
        if r.status_code != 200:
            return []
        rows = r.json()
        if not isinstance(rows, list):
            return []
        for _key in ("updated_at", "created_at", "inserted_at"):
            if rows and _key in rows[0]:
                rows.sort(key=lambda row: row.get(_key) or "", reverse=True)
                break
        return rows
    except Exception:
        return []


def delete_project(user_id: str, row_id: str) -> bool:
    """Delete one saved project row (scoped to this user)."""
    try:
        r = _req.delete(
            f"{_sb_url()}/rest/v1/user_projects",
            params={"user_id": f"eq.{user_id}", "id": f"eq.{row_id}"},
            headers=_db_hdr(), timeout=10,
        )
        return r.status_code in (200, 204)
    except Exception:
        return False


def load_latest_project(user_id: str):
    """Return (project_data, row_id) for the most recently saved project, or
    (None, None). Used to restore session state after a refresh/back button."""
    rows = list_projects(user_id)
    if rows and rows[0].get("project_data"):
        return rows[0]["project_data"], rows[0].get("id")
    return None, None


def load_project(user_id: str) -> Optional[dict]:
    """Back-compat wrapper — returns just the project dict for the most
    recently saved project."""
    data, _ = load_latest_project(user_id)
    return data


# ── Password reset form ───────────────────────────────────────
def _render_reset_password_form(access_token: str, refresh_token: str):
    """Shown when user arrives via Supabase password-reset email link."""
    st.markdown("""
    <style>
    html, body, [class*="css"] { font-family: 'Inter', sans-serif !important; background-color: #f5f7f5 !important; }
    [data-testid="stAppViewContainer"], [data-testid="stMain"], .main, .stApp { background-color: #f5f7f5 !important; }
    #MainMenu { visibility: hidden !important; } footer { visibility: hidden !important; } header { visibility: hidden !important; }
    .stButton > button {
        background: linear-gradient(135deg, #1d9e52, #145f34) !important;
        color: #fff !important; border: none !important; border-radius: 9px !important;
        font-weight: 700 !important; width: 100% !important;
    }
    .stTextInput > div > input {
        background: #ffffff !important; border: 1.5px solid #d4e0d4 !important; border-radius: 9px !important;
    }
    </style>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div style="text-align:center;margin-top:3rem;margin-bottom:2rem;">
      <span style="font-size:1.6rem;font-weight:800;color:#1a2e1a;letter-spacing:-0.03em;">Set new password</span><br>
      <span style="font-size:0.85rem;color:#5a7a5a;">Choose a new password for your PVMath account.</span>
    </div>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 1.4, 1])
    with col2:
        new_pass  = st.text_input("New password", type="password", key="reset_pass1", placeholder="Min. 8 characters")
        new_pass2 = st.text_input("Confirm password", type="password", key="reset_pass2", placeholder="Repeat password")

        if st.button("Update Password →", key="btn_reset"):
            if not new_pass or not new_pass2:
                st.error("Please enter and confirm your new password.")
            elif len(new_pass) < 8:
                st.error("Password must be at least 8 characters.")
            elif new_pass != new_pass2:
                st.error("Passwords do not match.")
            elif not access_token:
                st.error("Reset link is invalid or expired. Please request a new one.")
            else:
                with st.spinner("Updating password…"):
                    result = update_password(access_token, refresh_token, new_pass)
                if result["success"]:
                    st.success("✅ Password updated! You can now log in with your new password.")
                    # Clear recovery params
                    st.query_params.clear()
                else:
                    st.error(f"Failed to update password: {result.get('error', 'Unknown error')}. The link may have expired — request a new reset email.")


# ── Auth UI ───────────────────────────────────────────────────
def render_auth_page(app_name: str = "PVMath"):
    """
    Renders a full-page login / register UI.
    Returns True if user is authenticated, False otherwise.
    Call at the top of each Streamlit app.
    """

    # ── Auto-restore session from URL param (survives browser refresh / back) ──
    if not st.session_state.get("pvm_user_id"):
        _stored_rt = st.query_params.get("s", "")
        if _stored_rt:
            _restored = _refresh_session(_stored_rt)
            if _restored.get("success"):
                st.session_state["pvm_user_id"]      = _restored["user_id"]
                st.session_state["pvm_email"]        = _restored["email"]
                st.session_state["pvm_access_token"] = _restored["access_token"]
                # Keep an in-memory copy too — Streamlit's multipage navigation
                # can silently strip "s" from the visible URL on a page switch
                # (frontend-only; known Streamlit behavior), so app.py re-asserts
                # it from this session_state copy at the end of every script run.
                st.session_state["pvm_refresh_token"] = _restored["refresh_token"]
                st.session_state["pvm_token_refreshed_at"] = time.time()
                # Update param with rotated refresh token
                st.query_params["s"] = _restored["refresh_token"]
            elif not _restored.get("retry"):
                # Supabase explicitly rejected the token — it's genuinely dead.
                st.query_params.clear()
            # else: transient network/timeout error — leave "s" in the URL
            # untouched. Wiping it here on a hiccup is what was forcing a full
            # re-login on every refresh, even when the token was still good.

    # ── Proactively refresh a stale access token ──────────────────────────
    # _db_hdr() (used by every /rest/v1 call — list_projects, get_usage,
    # save_project, increment_usage, is_admin, get_profile, ...) sends
    # pvm_access_token as the bearer token. Supabase access tokens expire
    # after ~1 hour, but pvm_user_id/pvm_email stay in session_state
    # indefinitely (this is a long-running Streamlit session, no full page
    # reload between page switches). Once the token goes stale, every DB
    # read/write gets silently rejected — and get_usage()/list_projects()
    # swallow that failure and return 0/[] with no visible error, which is
    # exactly what made Overview show "0 projects / 0 analyses" for an
    # account that, per direct Supabase inspection, genuinely had both.
    # The earlier Save Project fix only refreshed when pvm_user_id was
    # EMPTY — it never covered "uid present, token just expired", which is
    # the far more common case in a tab that's been open for a while. This
    # closes that gap by refreshing proactively, well before the 1-hour
    # mark, instead of waiting for a symptom to show up.
    if st.session_state.get("pvm_user_id"):
        _last_refresh = st.session_state.get("pvm_token_refreshed_at")
        # _last_refresh is None covers two cases that both need a refresh
        # right now rather than being assumed fresh: a brand-new login (rare
        # — those call sites already hand us a brand-new token), and — far
        # more commonly — a session that was already open with an already-
        # stale token at the moment this fix was deployed. Treating "unknown
        # age" as "assume fresh" was the bug in the first version of this
        # check: it just started the clock from a token that might already
        # be dead, papering over the exact symptom for another 45 minutes
        # instead of fixing it immediately. So: unknown age or >45 min old
        # both trigger an actual refresh attempt; only the complete absence
        # of a refresh token to retry with falls back to just stamping time.
        if _last_refresh is None or time.time() - _last_refresh > 2700:  # 45 min,
            # safely under Supabase's default 1-hour access-token lifetime.
            _rt = st.session_state.get("pvm_refresh_token", "") or st.query_params.get("s", "")
            if _rt:
                _refreshed = _refresh_session(_rt)
                if _refreshed.get("success"):
                    st.session_state["pvm_access_token"]      = _refreshed["access_token"]
                    st.session_state["pvm_refresh_token"]     = _refreshed["refresh_token"]
                    st.session_state["pvm_token_refreshed_at"] = time.time()
                    st.query_params["s"] = _refreshed["refresh_token"]
                else:
                    # Refresh failed. If we don't even know the token's age
                    # (first time we've checked), don't loop retrying on
                    # every single rerun — stamp now and let the normal
                    # 45-min cycle handle the next attempt. If we DO know it
                    # was already overdue, leave the timestamp alone so the
                    # next page load tries again immediately instead of
                    # waiting another 45 minutes on a session that's clearly
                    # already in trouble.
                    if _last_refresh is None:
                        st.session_state["pvm_token_refreshed_at"] = time.time()
            else:
                st.session_state["pvm_token_refreshed_at"] = time.time()

    # Already logged in?
    if st.session_state.get("pvm_user_id"):
        if not st.session_state.get("pvm_email"):
            try:
                token = st.session_state.get("pvm_access_token", "")
                r = _req.get(f"{_sb_url()}/auth/v1/user",
                             headers=_auth_hdr(token), timeout=10)
                if r.status_code == 200:
                    st.session_state["pvm_email"] = r.json().get("email", "")
            except Exception:
                pass
        return True

    # ── OTP verification screen ────────────────────────────────
    if st.session_state.get("pvm_otp_state") == "pending":
        _otp_email    = st.session_state.get("pvm_otp_email", "")
        _otp_pass     = st.session_state.get("pvm_otp_password", "")
        _otp_code     = st.session_state.get("pvm_otp_code", "")
        _otp_expiry   = st.session_state.get("pvm_otp_expiry", 0)
        _otp_attempts = st.session_state.get("pvm_otp_attempts", 0)

        # Re-apply minimal styles (sidebar hidden, fonts, bg)
        st.markdown("""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&display=swap');
        html,body,[class*="css"]{font-family:'Inter',sans-serif!important;background:#f5f7f5!important;}
        [data-testid="stAppViewContainer"],[data-testid="stMain"],.main,.stApp{background:#f5f7f5!important;}
        #MainMenu,footer,header{visibility:hidden!important;}
        .block-container{padding-top:0!important;max-width:100%!important;}
        .stButton>button{
          background:linear-gradient(135deg,#1d9e52,#145f34)!important;
          color:#fff!important;border:none!important;border-radius:9px!important;
          font-weight:700!important;width:100%!important;
          box-shadow:0 2px 10px rgba(29,158,82,.25)!important;
        }
        .stTextInput>div>input{
          background:#fff!important;border:1.5px solid #d4e0d4!important;
          border-radius:9px!important;font-size:1.4rem!important;
          letter-spacing:0.25em!important;text-align:center!important;
          font-weight:700!important;color:#1a2e1a!important;
        }
        .stTextInput>div>input:focus{border-color:#1d9e52!important;
          box-shadow:0 0 0 3px rgba(29,158,82,.12)!important;}
        </style>
        """, unsafe_allow_html=True)

        st.markdown("""
        <div style="text-align:center;margin-top:3rem;margin-bottom:0.5rem;">
          <a href="https://pvmath.com" target="_blank" style="display:flex;align-items:center;gap:0.6rem;justify-content:center;margin-bottom:0.4rem;text-decoration:none;">
            <svg width="40" height="40" viewBox="0 0 46 46" xmlns="http://www.w3.org/2000/svg">
              <rect width="46" height="46" rx="10" fill="#145f34"/>
              <path d="M0 10 Q0 0 10 0 H36 Q46 0 46 10 V14 H0 Z" fill="#1d9e52"/>
              <text x="23" y="32" text-anchor="middle" dominant-baseline="middle"
                    font-family="Arial Black,Arial,sans-serif" font-size="18"
                    font-weight="900" fill="white">PV</text>
            </svg>
            <span style="font-size:1.5rem;font-weight:800;color:#1a2e1a;letter-spacing:-0.04em;">PVMath</span>
          </a>
        </div>
        """, unsafe_allow_html=True)

        col1, col2, col3 = st.columns([1, 1.4, 1])
        with col2:
            st.markdown(f"""
            <div style="text-align:center;background:#fff;border:1px solid #d4e0d4;
                        border-radius:14px;padding:2rem 2rem 1.5rem;margin-bottom:1.2rem;">
              <div style="font-size:2rem;margin-bottom:0.6rem;">📬</div>
              <div style="font-size:1.05rem;font-weight:800;color:#1a2e1a;margin-bottom:0.4rem;">
                Check your inbox
              </div>
              <div style="font-size:0.84rem;color:#5a7a5a;line-height:1.5;">
                We sent a 6-digit code to<br>
                <strong style="color:#1a2e1a;">{_otp_email}</strong>
              </div>
              <div style="font-size:0.75rem;color:#888;margin-top:0.6rem;">
                Also check spam / junk folder.
              </div>
            </div>
            """, unsafe_allow_html=True)

            if time.time() > _otp_expiry:
                st.error("Code expired.")
                if st.button("Send new code →", key="btn_otp_regen"):
                    _new = generate_otp()
                    st.session_state["pvm_otp_code"]     = _new
                    st.session_state["pvm_otp_expiry"]   = time.time() + 600
                    st.session_state["pvm_otp_attempts"] = 0
                    with st.spinner("Sending…"):
                        send_otp_email(_otp_email, _new)
                    st.success("New code sent!")
                    st.rerun()
            elif _otp_attempts >= 5:
                st.error("Too many incorrect attempts. Request a new code.")
                if st.button("Send new code →", key="btn_otp_regen_b"):
                    _new = generate_otp()
                    st.session_state["pvm_otp_code"]     = _new
                    st.session_state["pvm_otp_expiry"]   = time.time() + 600
                    st.session_state["pvm_otp_attempts"] = 0
                    with st.spinner("Sending…"):
                        send_otp_email(_otp_email, _new)
                    st.success("New code sent!")
                    st.rerun()
            else:
                otp_input = st.text_input(
                    "Verification code", key="otp_input_field",
                    placeholder="• • • • • •", max_chars=6
                )

                cola, colb = st.columns(2)
                with cola:
                    if st.button("Verify →", key="btn_otp_verify"):
                        if otp_input.strip() == _otp_code:
                            # Use pre-stored token from auto-confirm, or sign in fresh
                            _pre_token = st.session_state.get("pvm_otp_token", "")
                            _pre_uid   = st.session_state.get("pvm_otp_uid", "")
                            if _pre_token and _pre_uid:
                                for k in ["pvm_otp_state", "pvm_otp_email", "pvm_otp_password",
                                          "pvm_otp_code", "pvm_otp_expiry", "pvm_otp_attempts",
                                          "pvm_otp_token", "pvm_otp_uid"]:
                                    st.session_state.pop(k, None)
                                st.session_state["pvm_user_id"]      = _pre_uid
                                st.session_state["pvm_email"]        = _otp_email
                                st.session_state["pvm_access_token"] = _pre_token
                                st.rerun()
                            else:
                                with st.spinner("Verified! Logging in…"):
                                    result = sign_in(_otp_email, _otp_pass)
                                if result["success"]:
                                    for k in ["pvm_otp_state", "pvm_otp_email",
                                              "pvm_otp_password", "pvm_otp_code",
                                              "pvm_otp_expiry", "pvm_otp_attempts"]:
                                        st.session_state.pop(k, None)
                                    st.session_state["pvm_user_id"]      = result["user"].get("id")
                                    st.session_state["pvm_email"]        = result["user"].get("email")
                                    st.session_state["pvm_access_token"] = result.get("access_token", "")
                                    if result.get("refresh_token"):
                                        st.session_state["pvm_refresh_token"] = result["refresh_token"]
                                        st.query_params["s"] = result["refresh_token"]
                                    st.rerun()
                                else:
                                    st.error("Login error — please contact support.")
                        else:
                            st.session_state["pvm_otp_attempts"] += 1
                            left = 5 - st.session_state["pvm_otp_attempts"]
                            st.error(f"Incorrect code. {left} attempt(s) remaining.")
                with colb:
                    if st.button("Resend code", key="btn_otp_resend"):
                        _new = generate_otp()
                        st.session_state["pvm_otp_code"]     = _new
                        st.session_state["pvm_otp_expiry"]   = time.time() + 600
                        st.session_state["pvm_otp_attempts"] = 0
                        with st.spinner("Sending…"):
                            send_otp_email(_otp_email, _new)
                        st.success("New code sent!")
                        st.rerun()

            st.markdown("<div style='margin-top:0.8rem;'></div>", unsafe_allow_html=True)
            if st.button("← Back to login", key="btn_otp_back"):
                for k in ["pvm_otp_state", "pvm_otp_email", "pvm_otp_password",
                          "pvm_otp_code", "pvm_otp_expiry", "pvm_otp_attempts",
                          "pvm_user_id", "pvm_email", "pvm_access_token"]:
                    st.session_state.pop(k, None)
                st.rerun()

        return False

    # ── Password recovery mode ─────────────────────────────────
    # Supabase sends access_token in URL fragment (#); JS converts to query params
    params = st.query_params
    if params.get("type") == "recovery":
        _render_reset_password_form(
            params.get("access_token", ""),
            params.get("refresh_token", "")
        )
        return False

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

    /* st.form_submit_button renders separately from st.button — match the same style
       so the Log In button inside the form looks identical to every other button. */
    [data-testid="stFormSubmitButton"] > button {
        background: linear-gradient(135deg, #1d9e52, #145f34) !important;
        color: #fff !important; border: none !important;
        border-radius: 9px !important; font-weight: 700 !important;
        font-size: 0.92rem !important; padding: 0.72rem 1rem !important;
        width: 100% !important; transition: all .2s !important;
        letter-spacing: 0.01em !important;
        box-shadow: 0 2px 10px rgba(29,158,82,.25) !important;
    }
    [data-testid="stFormSubmitButton"] > button:hover {
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
    // Convert Supabase recovery fragment (#access_token=...) to query params
    (function() {
      if (window.location.hash && window.location.hash.includes('type=recovery')) {
        var params = new URLSearchParams(window.location.hash.slice(1));
        window.location.replace(window.location.pathname + '?' + params.toString());
      }
    })();

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
      <a href="https://pvmath.com" target="_blank" style="display:flex;align-items:center;gap:0.7rem;justify-content:center;margin-bottom:0.4rem;text-decoration:none;">
        <svg width="46" height="46" viewBox="0 0 46 46" xmlns="http://www.w3.org/2000/svg" style="flex-shrink:0;display:block;">
          <rect width="46" height="46" rx="10" fill="#145f34"/>
          <path d="M0 10 Q0 0 10 0 H36 Q46 0 46 10 V14 H0 Z" fill="#1d9e52"/>
          <text x="23" y="32" text-anchor="middle" dominant-baseline="middle" font-family="Arial Black,Arial,sans-serif" font-size="18" font-weight="900" fill="white">PV</text>
        </svg>
        <span style="font-family:Inter,sans-serif;font-size:1.7rem;font-weight:800;color:#1a2e1a;letter-spacing:-0.04em;">PVMath</span>
      </a>
      <div class="auth-logo-sub">Solar Site Intelligence &nbsp;·&nbsp; SiteIQ · TopoIQ · YieldIQ</div>
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
                        # OTP disabled — Brevo not yet activated. Re-enable once confirmed.
                        # Direct login using token from Supabase auto-confirm.
                        if result.get("access_token"):
                            st.session_state["pvm_user_id"]      = result["user"].get("id")
                            st.session_state["pvm_email"]        = result["user"].get("email") or reg_email
                            st.session_state["pvm_access_token"] = result["access_token"]
                            if result.get("refresh_token"):
                                st.session_state["pvm_refresh_token"] = result["refresh_token"]
                                st.query_params["s"] = result["refresh_token"]
                        else:
                            # Fallback: sign in with password
                            _r = sign_in(reg_email, reg_pass)
                            if _r["success"]:
                                st.session_state["pvm_user_id"]      = _r["user"].get("id")
                                st.session_state["pvm_email"]        = _r["user"].get("email")
                                st.session_state["pvm_access_token"] = _r.get("access_token", "")
                                if _r.get("refresh_token"):
                                    st.session_state["pvm_refresh_token"] = _r["refresh_token"]
                                    st.query_params["s"] = _r["refresh_token"]
                        st.rerun()
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

            # NOTE: wrapped in st.form so the Enter key submits the login (Streamlit
            # only treats Enter as "click the button" for widgets inside a real
            # st.form — plain st.text_input + st.button never responds to Enter).
            with st.form("login_form", clear_on_submit=False):
                login_email = st.text_input("Email address", key="login_email", placeholder="you@company.com")
                login_pass  = st.text_input("Password", key="login_pass", type="password", placeholder="Your password")
                login_submitted = st.form_submit_button("Log In →")

            # Tell the browser's own password manager what these fields are, so it
            # offers to save + autofill them next time. Streamlit doesn't set
            # autocomplete/name on its <input> tags by default, which is why
            # Chrome/Safari/Edge never remembered the email here before.
            st.markdown("""
            <script>
            (function () {
              function tagLoginFields() {
                document.querySelectorAll('[data-testid="stForm"] input[type="text"]').forEach(function(el){
                  el.setAttribute('autocomplete', 'username');
                  el.setAttribute('name', 'email');
                });
                document.querySelectorAll('[data-testid="stForm"] input[type="password"]').forEach(function(el){
                  el.setAttribute('autocomplete', 'current-password');
                  el.setAttribute('name', 'password');
                });
              }
              tagLoginFields();
              new MutationObserver(tagLoginFields).observe(document.body, {childList: true, subtree: true});
            })();
            </script>
            """, unsafe_allow_html=True)

            if login_submitted:
                if not login_email or not login_pass:
                    st.error("Please enter your email and password.")
                else:
                    with st.spinner("Logging in…"):
                        result = sign_in(login_email, login_pass)
                    if result["success"]:
                        st.session_state["pvm_user_id"]      = result["user"].get("id")
                        st.session_state["pvm_email"]        = result["user"].get("email")
                        st.session_state["pvm_access_token"] = result.get("access_token", "")
                        if result.get("refresh_token"):
                            st.session_state["pvm_refresh_token"] = result["refresh_token"]
                            st.query_params["s"] = result["refresh_token"]
                        st.rerun()
                    elif result.get("error") == "email_not_confirmed":
                        # Shouldn't happen with email confirmation disabled,
                        # but handle gracefully — send them an OTP to verify
                        _otp = generate_otp()
                        st.session_state["pvm_otp_state"]    = "pending"
                        st.session_state["pvm_otp_email"]    = login_email
                        st.session_state["pvm_otp_password"] = login_pass
                        st.session_state["pvm_otp_code"]     = _otp
                        st.session_state["pvm_otp_expiry"]   = time.time() + 600
                        st.session_state["pvm_otp_attempts"] = 0
                        with st.spinner("Sending verification code…"):
                            send_otp_email(login_email, _otp)
                        st.rerun()
                    else:
                        st.error("Incorrect email or password.")

            # ── Forgot password ───────────────────────────────
            st.markdown("<div style='margin-top:0.5rem;'></div>", unsafe_allow_html=True)
            if st.toggle("Forgot password?", key="toggle_forgot"):
                forgot_email = st.text_input("Enter your account email", key="forgot_email", placeholder="you@company.com")
                if st.button("Send Reset Link →", key="btn_forgot"):
                    if not forgot_email:
                        st.error("Please enter your email address.")
                    else:
                        with st.spinner("Sending reset email…"):
                            result = reset_password_email(forgot_email)
                        if result["success"]:
                            st.success("✅ Reset link sent — check your inbox. Click the link and you'll be brought back here to set a new password.")
                        else:
                            st.error(f"Failed to send reset email: {result.get('error', 'Unknown error')}")

        st.markdown("""
        <div class="auth-footer">
          <a href="https://pvmath.com" target="_blank">pvmath.com</a>
          &nbsp;·&nbsp; Solar Site Intelligence
          &nbsp;·&nbsp; <a href="mailto:contact@pvmath.com">contact@pvmath.com</a>
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
    """Renders the upgrade/limit-reached paywall. Call sites only ever pass
    app_label, so the user's plan is read from session state — that way the
    copy matches whatever was actually hit (free trial vs. a paid plan's
    monthly cap) instead of always claiming Professional is unlimited."""
    user_id = st.session_state.get("pvm_user_id", "guest")
    plan = get_plan(user_id)
    limit = plan_limit(plan)

    if plan == "free":
        title = "Free trial complete"
        body = (f"You've used your {limit} free {app_label} analyses. "
                f"Upgrade to Professional for {PLAN_LIMITS['professional']} analyses/month.")
        cta_text, cta_href = "Upgrade to Professional →", STRIPE_LINK
    else:
        title = "Monthly limit reached"
        body = (f"You've used all {limit} {plan_label(plan)} {app_label} analyses for this month. "
                f"Your limit resets at the start of next month.")
        cta_text, cta_href = "Contact us about a higher limit →", "mailto:contact@pvmath.com"

    st.markdown(f"""
    <div style="
        background: #fff; border: 1.5px solid #1d9e52; border-radius: 14px;
        padding: 2rem 2rem 1.8rem; text-align: center; margin: 2rem 0;
        box-shadow: 0 4px 24px rgba(29,158,82,.1);
    ">
      <div style="font-size:2rem;margin-bottom:0.8rem;">🔒</div>
      <div style="font-size:1.1rem;font-weight:800;color:#1a2e1a;letter-spacing:-0.02em;margin-bottom:0.5rem;">
        {title}
      </div>
      <div style="font-size:0.88rem;color:#5a7a5a;line-height:1.6;margin-bottom:1.5rem;max-width:340px;margin-left:auto;margin-right:auto;">
        {body}
      </div>
      <a href="{cta_href}" target="_blank" style="
          display:inline-block;
          background:linear-gradient(135deg,#1d9e52,#145f34);
          color:#fff;text-decoration:none;padding:0.8rem 2rem;
          border-radius:9px;font-weight:700;font-size:0.95rem;
          box-shadow:0 4px 16px rgba(29,158,82,.3);
      ">{cta_text}</a>
      <div style="font-size:0.75rem;color:#5a7a5a;margin-top:1rem;">
        Cancel anytime &nbsp;·&nbsp; All modules included &nbsp;·&nbsp; VAT invoice provided
      </div>
    </div>
    """, unsafe_allow_html=True)
