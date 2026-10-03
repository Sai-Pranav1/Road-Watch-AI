"""
API Router: Analytics & KPI Stats
Provides real-time metrics for the Authority Admin Dashboard.
"""

from fastapi import APIRouter
from app.database import db_service

router = APIRouter(prefix="/api/v1/stats", tags=["Dashboard Analytics"])


@router.get("")
async def get_dashboard_stats():
    """Returns high-level statistics for the admin dashboard KPI cards."""
    return db_service.get_stats()
