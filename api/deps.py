"""FastAPI dependencies — Supabase JWT auth."""

from __future__ import annotations

import os

from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from pvmath_supabase import AuthUser, verify_access_token, is_admin

_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> AuthUser:
    if os.environ.get("PVMATH_API_SKIP_AUTH", "").strip() in ("1", "true", "yes"):
        return AuthUser(
            user_id="dev-bypass",
            email="dev@local",
            access_token="",
            is_admin=True,
        )

    if not credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header. Use: Bearer <access_token>",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    try:
        user = verify_access_token(token)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    user_id = user["id"]
    email = user.get("email") or ""
    return AuthUser(
        user_id=user_id,
        email=email,
        access_token=token,
        is_admin=is_admin(user_id, token),
    )
