"""Signup OTP store + helpers (shared by API and Streamlit)."""

from __future__ import annotations

import hashlib
import secrets
import threading
import time
from typing import Any

from pvmath_auth import generate_otp, send_otp_email

OTP_TTL_SEC = 600
MAX_ATTEMPTS = 5

_lock = threading.Lock()
_pending: dict[str, dict[str, Any]] = {}


def _key(email: str) -> str:
    return email.strip().lower()


def _hash_code(code: str) -> str:
    return hashlib.sha256(code.strip().encode()).hexdigest()


def _purge_expired() -> None:
    now = time.time()
    expired = [k for k, v in _pending.items() if v.get("expiry", 0) < now]
    for k in expired:
        _pending.pop(k, None)


def start_signup_otp(
    email: str,
    *,
    access_token: str = "",
    refresh_token: str = "",
    expires_at: int = 0,
    user_id: str = "",
    password: str = "",
) -> dict:
    """Generate OTP, email it, and hold session fields until verified."""
    email = email.strip()
    code = generate_otp()
    with _lock:
        _purge_expired()
        _pending[_key(email)] = {
            "otp_hash": _hash_code(code),
            "expiry": time.time() + OTP_TTL_SEC,
            "attempts": 0,
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_at": expires_at,
            "user_id": user_id,
            "password": password,
        }
    sent = send_otp_email(email, code)
    if not sent.get("success"):
        with _lock:
            _pending.pop(_key(email), None)
        return {"success": False, "error": sent.get("error", "Could not send verification email")}
    return {"success": True}


def resend_signup_otp(email: str) -> dict:
    email = email.strip()
    with _lock:
        _purge_expired()
        entry = _pending.get(_key(email))
        if not entry:
            return {"success": False, "error": "No pending verification for this email — register again."}
        code = generate_otp()
        entry["otp_hash"] = _hash_code(code)
        entry["expiry"] = time.time() + OTP_TTL_SEC
        entry["attempts"] = 0
    sent = send_otp_email(email, code)
    if not sent.get("success"):
        return {"success": False, "error": sent.get("error", "Could not resend verification email")}
    return {"success": True}


def verify_signup_otp(email: str, code: str) -> dict:
    email = email.strip()
    with _lock:
        _purge_expired()
        entry = _pending.get(_key(email))
        if not entry:
            return {"success": False, "error": "No pending verification — register again or request a new code."}
        if time.time() > entry["expiry"]:
            _pending.pop(_key(email), None)
            return {"success": False, "error": "Code expired — request a new one."}
        if entry["attempts"] >= MAX_ATTEMPTS:
            return {"success": False, "error": "Too many attempts — request a new code."}
        if _hash_code(code) != entry["otp_hash"]:
            entry["attempts"] += 1
            left = MAX_ATTEMPTS - entry["attempts"]
            return {"success": False, "error": f"Incorrect code. {left} attempt(s) remaining."}
        session = {
            "access_token": entry.get("access_token", ""),
            "refresh_token": entry.get("refresh_token", ""),
            "expires_at": entry.get("expires_at", 0),
            "user_id": entry.get("user_id", ""),
            "password": entry.get("password", ""),
        }
        _pending.pop(_key(email), None)
    return {"success": True, **session}
