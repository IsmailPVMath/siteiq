"""Screening PDF download from gate results."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import Response

from api.deps import get_current_user
from api.schemas.gate import GateAnalyzeResponse
from pvmath_gate.screening_pdf import build_screening_pdf
from pvmath_supabase import AuthUser

router = APIRouter(tags=["reports"])


@router.post("/reports/screening-pdf")
def screening_pdf(
    body: GateAnalyzeResponse,
    _user: AuthUser = Depends(get_current_user),
):
    pdf_bytes = build_screening_pdf(body.model_dump())
    safe = (body.project_name or "screening").replace(" ", "_")[:80]
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="PVMath_{safe}.pdf"'},
    )
