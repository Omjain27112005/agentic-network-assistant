"""Alerts router — active alerts from Redis."""
from typing import List, Optional
from fastapi import APIRouter
from pydantic import BaseModel

from shared.redis_client import get_redis_client

router = APIRouter()


class AlertResponse(BaseModel):
    alert_id: str
    device_id: str
    alert_type: str
    severity: str
    threshold_breached: str
    metric_value: Optional[float] = None
    threshold_value: Optional[float] = None
    timestamp: str
    status: str
    jira_ticket_id: Optional[str] = None
    root_cause: Optional[str] = None


@router.get("/alerts", response_model=List[AlertResponse])
async def get_active_alerts():
    """Get all currently active alerts from Redis."""
    redis = get_redis_client()
    raw_alerts = redis.get_all_active_alerts()

    result = []
    for a in raw_alerts:
        try:
            result.append(AlertResponse(
                alert_id=a.get("alert_id", ""),
                device_id=a.get("device_id", ""),
                alert_type=a.get("alert_type", ""),
                severity=a.get("severity", ""),
                threshold_breached=a.get("threshold_breached", ""),
                metric_value=float(a["metric_value"]) if a.get("metric_value") else None,
                threshold_value=float(a["threshold_value"]) if a.get("threshold_value") else None,
                timestamp=a.get("timestamp", ""),
                status=a.get("status", "OPEN"),
                jira_ticket_id=a.get("jira_ticket_id") or None,
                root_cause=a.get("root_cause") or None,
            ))
        except Exception:
            continue  # Skip malformed alerts

    # Sort: EMERGENCY first, then CRITICAL, then WARNING
    severity_order = {"EMERGENCY": 0, "CRITICAL": 1, "WARNING": 2, "INFO": 3}
    result.sort(key=lambda a: severity_order.get(a.severity, 4))

    return result


@router.get("/alerts/{alert_id}", response_model=AlertResponse)
async def get_alert(alert_id: str):
    """Get a specific alert by ID."""
    from fastapi import HTTPException
    redis = get_redis_client()
    a = redis.get_alert(alert_id)
    if not a:
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")

    return AlertResponse(
        alert_id=a.get("alert_id", ""),
        device_id=a.get("device_id", ""),
        alert_type=a.get("alert_type", ""),
        severity=a.get("severity", ""),
        threshold_breached=a.get("threshold_breached", ""),
        metric_value=float(a["metric_value"]) if a.get("metric_value") else None,
        threshold_value=float(a["threshold_value"]) if a.get("threshold_value") else None,
        timestamp=a.get("timestamp", ""),
        status=a.get("status", "OPEN"),
        jira_ticket_id=a.get("jira_ticket_id") or None,
        root_cause=a.get("root_cause") or None,
    )
