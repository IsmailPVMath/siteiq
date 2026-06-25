"""Supabase REST helpers for API services (no Streamlit dependency)."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Optional

import requests

PLAN_LIMITS = {
    "free": 5,
    "professional": 75,
    "developer": 300,
    "enterprise": None,
}
DEFAULT_PLAN = "free"
PLAN_LIMIT_MODE = {
    "free": "per_module",
    "professional": "pooled",
    "developer": "pooled",
    "enterprise": None,
}
USAGE_APPS = ("siteiq", "topoiq", "yieldiq")


def sb_url() -> str:
    url = os.environ.get("SUPABASE_URL", "").strip()
    if not url:
        raise RuntimeError("SUPABASE_URL is not set")
    return url.rstrip("/")


def sb_key() -> str:
    key = os.environ.get("SUPABASE_KEY", "").strip()
    if not key:
        raise RuntimeError("SUPABASE_KEY is not set")
    return key


def auth_hdr(token: str = "") -> dict:
    headers = {"apikey": sb_key(), "Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def db_hdr(token: str) -> dict:
    key = sb_key()
    return {
        "apikey": key,
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def verify_access_token(token: str) -> dict:
    """Return Supabase user dict or raise ValueError."""
    if not token:
        raise ValueError("Missing access token")
    r = requests.get(
        f"{sb_url()}/auth/v1/user",
        headers=auth_hdr(token),
        timeout=10,
    )
    if r.status_code != 200:
        raise ValueError("Invalid or expired access token")
    user = r.json()
    if not user.get("id"):
        raise ValueError("Invalid user payload")
    return user


@dataclass
class AuthUser:
    user_id: str
    email: str
    access_token: str
    is_admin: bool = False


def _current_period() -> str:
    return time.strftime("%Y-%m")


def get_profile(user_id: str, token: str) -> dict:
    try:
        r = requests.get(
            f"{sb_url()}/rest/v1/profiles",
            params={"id": f"eq.{user_id}", "select": "plan,team_id,is_admin"},
            headers=db_hdr(token),
            timeout=10,
        )
        data = r.json()
        return data[0] if data else {}
    except Exception:
        return {}


def get_plan(user_id: str, token: str) -> str:
    return get_profile(user_id, token).get("plan") or DEFAULT_PLAN


def get_team_id(user_id: str, token: str):
    return get_profile(user_id, token).get("team_id") or None


def is_admin(user_id: str, token: str) -> bool:
    profile = get_profile(user_id, token)
    return bool(profile.get("is_admin"))


def plan_limit(plan: str) -> Optional[int]:
    return PLAN_LIMITS.get(plan, PLAN_LIMITS[DEFAULT_PLAN])


def plan_limit_mode(plan: str) -> str:
    mode = PLAN_LIMIT_MODE.get(plan, "per_module")
    return mode or "per_module"


def _usage_key(user_id: str, token: str) -> str:
    return get_team_id(user_id, token) or user_id


def get_usage(user_id: str, app: str, token: str) -> int:
    key, period = _usage_key(user_id, token), _current_period()
    try:
        r = requests.get(
            f"{sb_url()}/rest/v1/usage_tracking",
            params={
                "usage_key": f"eq.{key}",
                "app": f"eq.{app}",
                "period": f"eq.{period}",
                "select": "count",
            },
            headers=db_hdr(token),
            timeout=10,
        )
        data = r.json()
        return data[0]["count"] if data else 0
    except Exception:
        return 0


def get_total_usage(user_id: str, token: str) -> int:
    return sum(get_usage(user_id, app, token) for app in USAGE_APPS)


def increment_usage(user_id: str, app: str, token: str) -> int:
    key, period = _usage_key(user_id, token), _current_period()
    try:
        current = get_usage(user_id, app, token)
        new_count = current + 1
        base = f"{sb_url()}/rest/v1/usage_tracking"
        if current == 0:
            requests.post(
                base,
                json={
                    "user_id": user_id,
                    "usage_key": key,
                    "app": app,
                    "period": period,
                    "count": 1,
                },
                headers=db_hdr(token),
                timeout=10,
            )
        else:
            requests.patch(
                base,
                json={"count": new_count},
                params={
                    "usage_key": f"eq.{key}",
                    "app": f"eq.{app}",
                    "period": f"eq.{period}",
                },
                headers=db_hdr(token),
                timeout=10,
            )
        return new_count
    except Exception:
        return 0


def is_over_limit(user_id: str, app: str, token: str) -> bool:
    if is_admin(user_id, token):
        return False
    plan = get_plan(user_id, token)
    limit = plan_limit(plan)
    if limit is None:
        return False
    if plan_limit_mode(plan) == "pooled":
        return get_total_usage(user_id, token) >= limit
    return get_usage(user_id, app, token) >= limit


def usage_snapshot(user_id: str, token: str) -> dict:
    plan = get_plan(user_id, token)
    limit = plan_limit(plan)
    mode = plan_limit_mode(plan)
    per_app = {app: get_usage(user_id, app, token) for app in USAGE_APPS}
    total = sum(per_app.values())
    if is_admin(user_id, token) or limit is None:
        return {
            "plan": plan,
            "mode": mode,
            "limit": limit,
            "total": total,
            "per_app": per_app,
            "remaining": None,
            "at_limit": False,
        }
    if mode == "pooled":
        remaining = max(0, limit - total)
        return {
            "plan": plan,
            "mode": mode,
            "limit": limit,
            "total": total,
            "per_app": per_app,
            "remaining": remaining,
            "at_limit": total >= limit,
        }
    rem_siteiq = max(0, limit - per_app["siteiq"])
    return {
        "plan": plan,
        "mode": mode,
        "limit": limit,
        "total": total,
        "per_app": per_app,
        "remaining": rem_siteiq,
        "at_limit": per_app["siteiq"] >= limit,
    }
