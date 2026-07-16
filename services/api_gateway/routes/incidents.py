"""Incidents router — historical incidents from PostgreSQL."""
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from shared.config import get_settings
from services.action_executor.db import Database, get_recent_incidents

router = APIRouter()

# Lazy DB instance — initialized on first request
_db: Optional[Database] = None


def get_db() -> Database:
    global _db
    if _db is None:
        settings = get_settings()
        _db = Database(database_url=settings.database_url)
    return _db


class IncidentResponse(BaseModel):
    id: int
    alert_id: str
    device_id: str
    alert_type: str
    severity: str
    root_cause: Optional[str] = None
    confidence_score: Optional[float] = None
    recommendation: Optional[str] = None
    jira_ticket_id: Optional[str] = None
    resolved: bool
    created_at: Optional[str] = None
    resolved_at: Optional[str] = None


@router.get("/incidents", response_model=List[IncidentResponse])
async def get_incidents(limit: int = Query(default=50, le=200)):
    """Get recent incidents from PostgreSQL ordered by newest first."""
    try:
        db = get_db()
        incidents = get_recent_incidents(db, limit=limit)
        return [IncidentResponse(**i) for i in incidents]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)[:100]}")


@router.get("/incidents/stats")
async def get_incident_stats():
    """Get aggregate statistics about incidents."""
    try:
        from sqlalchemy import func, text as sql_text
        db = get_db()
        with db.session() as session:
            from services.action_executor.db import IncidentORM
            total = session.query(func.count(IncidentORM.id)).scalar()
            resolved = session.query(func.count(IncidentORM.id)).filter(IncidentORM.resolved == True).scalar()
            by_severity = session.query(
                IncidentORM.severity,
                func.count(IncidentORM.id)
            ).group_by(IncidentORM.severity).all()

            return {
                "total_incidents": total,
                "resolved": resolved,
                "open": total - resolved,
                "by_severity": {sev: count for sev, count in by_severity},
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Stats error: {str(e)[:100]}")
