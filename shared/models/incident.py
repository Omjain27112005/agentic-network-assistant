"""
Shared Pydantic model for Incidents.
Used by: Action Executor, API Gateway, AI Agent
"""
import json
from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field


class Incident(BaseModel):
    """
    A confirmed network incident — created by Action Executor
    after AI Agent completes its ReAct analysis.
    Stored permanently in PostgreSQL.
    """
    alert_id: str                               # Links back to the triggering alert
    device_id: str
    alert_type: str
    severity: str
    root_cause: Optional[str] = None            # AI-determined root cause
    confidence_score: Optional[float] = None    # AI confidence 0.0 to 1.0
    recommendation: Optional[str] = None        # AI recommended fix
    jira_ticket_id: Optional[str] = None        # Created Jira ticket ID
    resolved: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)
    resolved_at: Optional[datetime] = None
    raw_alert: Optional[dict] = None            # Full original alert payload


class AgentAction(BaseModel):
    """
    Audit log entry for every action taken by the AI Agent.
    Ensures full traceability of autonomous decisions.
    """
    incident_id: Optional[int] = None           # PostgreSQL incident row ID
    action_type: str                            # CREATE_TICKET | NOTIFY | LOG
    action_payload: dict = Field(default_factory=dict)
    success: bool = True
    error_message: Optional[str] = None
    executed_at: datetime = Field(default_factory=datetime.utcnow)

    def to_kafka_payload(self) -> str:
        """Serialize to JSON string for Kafka message value."""
        data = self.dict()
        data["executed_at"] = self.executed_at.isoformat()
        return json.dumps(data)
