"""Password login — proxies Supabase token for React POC (avoids browser CORS)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
import requests

from pvmath_auth import sign_in
from pvmath_otp import resend_signup_otp, start_signup_otp, verify_signup_otp
from pvmath_supabase import auth_hdr, sb_url

router = APIRouter(tags=["auth"])


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=200)
    password: str = Field(min_length=1, max_length=200)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1, max_length=4096)


class SignupRequest(BaseModel):
    email: str = Field(min_length=3, max_length=200)
    password: str = Field(min_length=8, max_length=200)
    first_name: str = Field(default="", max_length=80)
    last_name: str = Field(default="", max_length=80)


class SignupOtpRequest(BaseModel):
    email: str = Field(min_length=3, max_length=200)
    code: str = Field(min_length=6, max_length=6)


class SignupResendRequest(BaseModel):
    email: str = Field(min_length=3, max_length=200)


def _normalize_name_part(name: str) -> str:
    return " ".join(name.strip().split())


def _session_response(data: dict, email: str) -> dict:
    return {
        "access_token": data["access_token"],
        "refresh_token": data.get("refresh_token", ""),
        "expires_at": data.get("expires_at", 0),
        "user": {
            "id": data.get("user", {}).get("id", data.get("user_id", "")),
            "email": data.get("user", {}).get("email", email),
        },
    }


@router.post("/auth/signup")
def signup(body: SignupRequest):
    """Create a SiteIQ account and email a one-time verification code."""
    payload: dict = {"email": body.email.strip(), "password": body.password}
    fn = _normalize_name_part(body.first_name)
    ln = _normalize_name_part(body.last_name)
    if fn or ln:
        payload["data"] = {
            "first_name": fn,
            "last_name": ln,
            "full_name": f"{fn} {ln}".strip(),
        }
    try:
        r = requests.post(
            f"{sb_url()}/auth/v1/signup",
            json=payload,
            headers=auth_hdr(),
            timeout=15,
        )
    except requests.RequestException as exc:
        raise HTTPException(status_code=503, detail="Auth service unreachable") from exc

    data = r.json() if r.text else {}
    if r.status_code not in (200, 201):
        msg = (
            data.get("msg")
            or data.get("error_description")
            or data.get("message")
            or "Could not create account"
        )
        raise HTTPException(status_code=400, detail=str(msg))

    user = data.get("user") or {}
    user_id = user.get("id") or data.get("id") or ""
    email = user.get("email") or data.get("email") or body.email.strip()
    otp_result = start_signup_otp(
        email,
        access_token=data.get("access_token", ""),
        refresh_token=data.get("refresh_token", ""),
        expires_at=data.get("expires_at", 0),
        user_id=user_id,
        password=body.password,
    )
    if not otp_result.get("success"):
        raise HTTPException(
            status_code=503,
            detail=otp_result.get("error", "Could not send verification email"),
        )

    return {
        "otp_required": True,
        "email": email,
        "email_confirmation_required": True,
    }


@router.post("/auth/signup/verify")
def signup_verify(body: SignupOtpRequest):
    """Verify signup OTP and return a Supabase session."""
    result = verify_signup_otp(body.email, body.code)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Invalid code"))

    email = body.email.strip()
    access = result.get("access_token", "")
    refresh = result.get("refresh_token", "")
    expires_at = result.get("expires_at", 0)
    user_id = result.get("user_id", "")

    if not access:
        login = sign_in(email, result.get("password", ""))
        if not login.get("success"):
            raise HTTPException(status_code=400, detail="Verified but login failed — contact support.")
        user = login.get("user", {})
        return _session_response(
            {
                "access_token": login.get("access_token", ""),
                "refresh_token": login.get("refresh_token", ""),
                "expires_at": 0,
                "user": user,
                "user_id": user.get("id", user_id),
            },
            email,
        )

    return _session_response(
        {
            "access_token": access,
            "refresh_token": refresh,
            "expires_at": expires_at,
            "user": {"id": user_id, "email": email},
            "user_id": user_id,
        },
        email,
    )


@router.post("/auth/signup/resend")
def signup_resend(body: SignupResendRequest):
    """Resend signup verification code."""
    result = resend_signup_otp(body.email)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Could not resend code"))
    return {"success": True}


@router.post("/auth/login")
def login(body: LoginRequest):
    """Exchange email/password for Supabase access_token (same as SiteIQ account)."""
    try:
        r = requests.post(
            f"{sb_url()}/auth/v1/token?grant_type=password",
            json={"email": body.email, "password": body.password},
            headers=auth_hdr(),
            timeout=15,
        )
    except requests.RequestException as exc:
        raise HTTPException(
            status_code=503,
            detail="Auth service unreachable",
        ) from exc

    data = r.json() if r.text else {}
    if r.status_code != 200 or not data.get("access_token"):
        msg = (
            data.get("msg")
            or data.get("error_description")
            or data.get("message")
            or "Invalid email or password"
        )
        raise HTTPException(status_code=401, detail=str(msg))

    return {
        "access_token": data["access_token"],
        "refresh_token": data.get("refresh_token", ""),
        "expires_at": data.get("expires_at", 0),
        "user": {
            "id": data.get("user", {}).get("id", ""),
            "email": data.get("user", {}).get("email", body.email),
        },
    }


class PasswordResetRequest(BaseModel):
    email: str = Field(min_length=3, max_length=200)


@router.post("/auth/reset-password")
def reset_password(body: PasswordResetRequest):
    """Send a Supabase password-recovery email (always returns success — no account enumeration)."""
    try:
        requests.post(
            f"{sb_url()}/auth/v1/recover",
            json={"email": body.email.strip()},
            headers=auth_hdr(),
            timeout=15,
        )
    except requests.RequestException:
        pass
    return {"success": True}


@router.post("/auth/refresh")
def refresh_session(body: RefreshRequest):
    """Exchange a stored refresh token for a new Supabase session."""
    try:
        r = requests.post(
            f"{sb_url()}/auth/v1/token?grant_type=refresh_token",
            json={"refresh_token": body.refresh_token},
            headers=auth_hdr(),
            timeout=15,
        )
    except requests.RequestException as exc:
        raise HTTPException(
            status_code=503,
            detail="Auth service unreachable",
        ) from exc

    data = r.json() if r.text else {}
    if r.status_code != 200 or not data.get("access_token"):
        msg = (
            data.get("msg")
            or data.get("error_description")
            or data.get("message")
            or "Invalid or expired refresh token"
        )
        raise HTTPException(status_code=401, detail=str(msg))

    return {
        "access_token": data["access_token"],
        "refresh_token": data.get("refresh_token", body.refresh_token),
        "expires_at": data.get("expires_at", 0),
        "user": {
            "id": data.get("user", {}).get("id", ""),
            "email": data.get("user", {}).get("email", ""),
        },
    }
