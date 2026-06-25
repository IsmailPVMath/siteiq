"""Password login — proxies Supabase token for React POC (avoids browser CORS)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
import requests

from pvmath_supabase import auth_hdr, sb_url

router = APIRouter(tags=["auth"])


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=200)
    password: str = Field(min_length=1, max_length=200)


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
