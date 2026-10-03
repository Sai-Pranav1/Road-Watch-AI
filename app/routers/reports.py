"""
API Router: Reports CRUD & Triage Execution
Handles querying, status transitions, crew dispatch, demo seeding, and CSV exports.
"""

import io
import csv
import uuid
import datetime
import random
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel

from app.database import db_service
from app.priority_engine import calculate_priority_score

router = APIRouter(prefix="/api/v1/reports", tags=["Reports Management"])


class StatusUpdatePayload(BaseModel):
    status: str
    assigned_crew: Optional[str] = None
    notes: Optional[str] = None
    changed_by: Optional[str] = "Municipal Dispatcher"


@router.get("")
async def list_reports(
    status: Optional[str] = Query(None, description="Filter by status: Reported, Assigned, In Progress, Resolved"),
    severity: Optional[str] = Query(None, description="Filter by severity: Low, Medium, High, Critical"),
    min_priority: Optional[int] = Query(None, description="Minimum priority score threshold"),
    limit: int = Query(150, ge=1, le=500)
):
    """Fetches reports sorted by priority_score descending."""
    reports = db_service.get_reports(
        status=status,
        severity=severity,
        min_priority=min_priority,
        limit=limit
    )
    return {"count": len(reports), "reports": reports}


@router.get("/{report_id}")
async def get_report_detail(report_id: str):
    """Retrieves single report details."""
    report = db_service.get_report_by_id(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found.")
    return report


@router.patch("/{report_id}/status")
async def update_report_status(report_id: str, payload: StatusUpdatePayload):
    """
    Executes status progression in the triage queue:
    'Reported' -> 'Assigned' -> 'In Progress' -> 'Resolved'.
    Records the change in status_updates audit log.
    """
    valid_statuses = ["Reported", "Assigned", "In Progress", "Resolved"]
    if payload.status not in valid_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status '{payload.status}'. Allowed: {', '.join(valid_statuses)}"
        )

    updated = db_service.update_report_status(
        report_id=report_id,
        new_status=payload.status,
        assigned_crew=payload.assigned_crew,
        notes=payload.notes,
        changed_by=payload.changed_by or "Municipal Dispatcher"
    )

    if not updated:
        raise HTTPException(status_code=404, detail="Report not found.")

    return {
        "message": f"Report status successfully updated to {payload.status}",
        "report": updated
    }


@router.get("/export/csv")
async def export_reports_csv():
    """Generates and downloads a CSV export of all road damage reports."""
    reports = db_service.get_reports(limit=500)
    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "Report ID", "Status", "Damage Type", "Severity", "Priority Score",
        "Confidence", "Latitude", "Longitude", "Road Class", "Assigned Crew",
        "Created At", "Image URL"
    ])

    for r in reports:
        writer.writerow([
            r.get("id"),
            r.get("status"),
            r.get("damage_type"),
            r.get("severity"),
            r.get("priority_score"),
            r.get("confidence"),
            r.get("latitude"),
            r.get("longitude"),
            r.get("road_class"),
            r.get("assigned_crew", "Unassigned"),
            r.get("created_at"),
            r.get("image_url")
        ])

    csv_data = output.getvalue()
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=road_damage_triage_export.csv"}
    )
