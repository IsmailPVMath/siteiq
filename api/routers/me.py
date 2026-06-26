"""Authenticated user profile + usage."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.deps import get_current_user
from pvmath_auth import sign_in, update_password
from pvmath_supabase import AuthUser, usage_snapshot

router = APIRouter(tags=["auth"])


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=8, max_length=200)


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


@router.post("/me/password")
def change_password(body: ChangePasswordRequest, user: AuthUser = Depends(get_current_user)):
    verify = sign_in(user.email, body.current_password)
    if not verify.get("success"):
        raise HTTPException(status_code=400, detail="Current password is incorrect.")
    if not user.access_token:
        raise HTTPException(status_code=401, detail="Session expired — log in again.")
    result = update_password(user.access_token, "", body.new_password)
    if not result.get("success"):
        raise HTTPException(
            status_code=400,
            detail=result.get("error") or "Could not update password.",
        )
    return {"success": True, "message": "Password updated."}
