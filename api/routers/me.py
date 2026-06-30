"""Authenticated user profile + usage."""

from __future__ import annotations

import io

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from api.deps import get_current_user
from pvmath_auth import can_download_engineering_manual, sign_in, update_password
from pvmath_resources import KNOWLEDGE_CENTRE_URL, PUBLIC_MANUAL_FILENAME, load_public_manual_bytes
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
        "knowledge_centre_url": KNOWLEDGE_CENTRE_URL,
        "engineering_manual_available": can_download_engineering_manual(user.user_id),
    }


@router.get("/me/engineering-manual")
def engineering_manual(user: AuthUser = Depends(get_current_user)):
    """Professional+ Engineering Reference Manual (Word, public edition)."""
    if not can_download_engineering_manual(user.user_id):
        raise HTTPException(
            status_code=403,
            detail="Engineering Reference Manual requires Professional plan or above.",
        )
    data = load_public_manual_bytes()
    if not data:
        raise HTTPException(status_code=503, detail="Manual file unavailable — contact contact@pvmath.com.")
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{PUBLIC_MANUAL_FILENAME}"'},
    )


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
