"""Authenticated user profile + usage."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.deps import get_current_user
from pvmath_supabase import AuthUser, usage_snapshot

router = APIRouter(tags=["auth"])


@router.get("/me")
def me(user: AuthUser = Depends(get_current_user)):
    usage = usage_snapshot(user.user_id, user.access_token) if user.access_token else {
        "plan": "dev",
        "mode": "bypass",
        "limit": None,
        "total": 0,
        "per_app": {},
        "remaining": None,
        "at_limit": False,
    }
    return {
        "user_id": user.user_id,
        "email": user.email,
        "is_admin": user.is_admin,
        "usage": usage,
    }
