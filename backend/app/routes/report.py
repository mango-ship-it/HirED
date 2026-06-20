"""POST /report — the detailed summary/report page (3rd page).

Takes the data the frontend already collected (score, categories, lessons, skills,
percentile, resources) and returns a narrative report + a narratable slide deck,
enriched with Sai-sourced jobs/mentors. Templated — no API spend.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.models.report import ReportRequest, ReportResponse
from app.services.report_service import build_report

router = APIRouter()


@router.post("/report", response_model=ReportResponse)
async def report(request: ReportRequest) -> ReportResponse:
    return build_report(request)
