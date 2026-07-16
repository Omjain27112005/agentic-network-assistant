"""
Action Handler — orchestrates the full response to an AI Agent result.

This is the final step in the automated incident response pipeline.
When the AI Agent finishes its investigation and publishes to network.actions,
this handler:
  1. Decides whether to create a Jira ticket (based on severity + confidence)
  2. Creates the ticket if needed
  3. Saves the incident permanently to PostgreSQL
  4. Logs every action taken for full auditability
  5. Updates Redis alert status with the Jira ticket ID

Decision Logic:
  EMERGENCY  + any confidence   → Always create Jira ticket
  CRITICAL   + confidence ≥ 0.5 → Create Jira ticket
  CRITICAL   + confidence < 0.5 → Save incident, no ticket (needs human review)
  SUCCESS=False (agent failed)  → Save incident as unresolved, no ticket
"""
import json
from typing import Optional, Dict, Any

import structlog

from services.action_executor.jira_client import JiraClient
from services.action_executor.db import Database, save_incident, save_agent_action
from shared.redis_client import get_redis_client

logger = structlog.get_logger(__name__)

# Minimum confidence score to auto-create a Jira ticket for CRITICAL alerts
JIRA_TICKET_MIN_CONFIDENCE = 0.5


class ActionHandler:
    """
    Orchestrates the full action pipeline for a completed AI investigation.

    One handler instance shared across all messages (stateless per message).
    Dependencies (Jira client, DB) are injected at construction time.
    """

    def __init__(self, jira: JiraClient, db: Database):
        self._jira = jira
        self._db = db
        self._actions_executed = 0

    def handle(self, agent_result: Dict[str, Any], alert_data: Dict[str, Any]) -> None:
        """
        Execute all actions for a completed AI investigation.

        Args:
            agent_result: AgentResult dict from Kafka network.actions topic
            alert_data: Original alert dict (stored in agent_result or fetched)
        """
        alert_id = agent_result.get("alert_id", "UNKNOWN")
        device_id = agent_result.get("device_id", "UNKNOWN")
        severity = alert_data.get("severity", "CRITICAL")
        confidence = float(agent_result.get("confidence_score", 0.0))
        success = agent_result.get("success", False)

        self._actions_executed += 1

        logger.info(
            "action_handler.processing",
            alert_id=alert_id,
            device_id=device_id,
            severity=severity,
            confidence=confidence,
            agent_success=success,
            total_processed=self._actions_executed,
        )

        jira_ticket_id: Optional[str] = None
        jira_ticket_url: Optional[str] = None

        # -----------------------------------------------
        # Step 1: Decide whether to create Jira ticket
        # -----------------------------------------------
        should_create_ticket = self._should_create_ticket(severity, confidence, success)

        if should_create_ticket:
            ticket_result = self._create_jira_ticket(agent_result, alert_data, alert_id)
            if ticket_result:
                jira_ticket_id = ticket_result.get("ticket_id")
                jira_ticket_url = ticket_result.get("ticket_url")
        else:
            logger.info(
                "jira.ticket_skipped",
                alert_id=alert_id,
                severity=severity,
                confidence=confidence,
                agent_success=success,
                reason=self._skip_reason(severity, confidence, success),
            )
            # Log the skip as an action for auditability
            save_agent_action(
                db=self._db,
                incident_id=None,
                action_type="TICKET_SKIPPED",
                action_payload={
                    "alert_id": alert_id,
                    "reason": self._skip_reason(severity, confidence, success),
                    "severity": severity,
                    "confidence": confidence,
                },
                success=True,
            )

        # -----------------------------------------------
        # Step 2: Save incident to PostgreSQL
        # -----------------------------------------------
        incident_id = self._save_to_database(
            agent_result=agent_result,
            alert_data=alert_data,
            jira_ticket_id=jira_ticket_id,
        )

        # -----------------------------------------------
        # Step 3: Update Redis with Jira ticket ID
        # -----------------------------------------------
        if jira_ticket_id:
            self._update_redis_with_ticket(alert_id, jira_ticket_id)

        logger.info(
            "action_handler.complete",
            alert_id=alert_id,
            incident_id=incident_id,
            jira_ticket=jira_ticket_id or "none",
            jira_url=jira_ticket_url or "none",
        )

    # -----------------------------------------------
    # Private Methods
    # -----------------------------------------------

    def _should_create_ticket(self, severity: str, confidence: float, success: bool) -> bool:
        """
        Decision logic for Jira ticket creation.

        EMERGENCY: Always create (network is down — act immediately)
        CRITICAL + confidence ≥ 0.5 + agent succeeded: Create
        Everything else: Skip
        """
        if severity == "EMERGENCY":
            return True
        if severity == "CRITICAL" and success and confidence >= JIRA_TICKET_MIN_CONFIDENCE:
            return True
        return False

    def _skip_reason(self, severity: str, confidence: float, success: bool) -> str:
        if not success:
            return "Agent investigation failed — manual review required"
        if severity not in ("CRITICAL", "EMERGENCY"):
            return f"Severity {severity} does not require a ticket (only CRITICAL/EMERGENCY)"
        return f"Confidence {confidence:.0%} below threshold {JIRA_TICKET_MIN_CONFIDENCE:.0%}"

    def _create_jira_ticket(
        self,
        agent_result: dict,
        alert_data: dict,
        alert_id: str,
    ) -> Optional[dict]:
        """Create a Jira ticket and log the action."""
        try:
            result = self._jira.create_incident_ticket(agent_result, alert_data)

            if result:
                save_agent_action(
                    db=self._db,
                    incident_id=None,  # Will update after incident saved
                    action_type="CREATE_JIRA_TICKET",
                    action_payload={
                        "alert_id": alert_id,
                        "ticket_id": result.get("ticket_id"),
                        "ticket_url": result.get("ticket_url"),
                        "severity": alert_data.get("severity"),
                    },
                    success=True,
                )
                logger.info(
                    "jira.ticket_created_successfully",
                    alert_id=alert_id,
                    ticket_id=result.get("ticket_id"),
                    ticket_url=result.get("ticket_url"),
                )
                return result

            else:
                save_agent_action(
                    db=self._db,
                    incident_id=None,
                    action_type="CREATE_JIRA_TICKET",
                    action_payload={"alert_id": alert_id},
                    success=False,
                    error_message="Jira API returned no result",
                )
                return None

        except Exception as e:
            logger.error("jira.ticket_creation_failed", alert_id=alert_id, error=str(e))
            save_agent_action(
                db=self._db,
                incident_id=None,
                action_type="CREATE_JIRA_TICKET",
                action_payload={"alert_id": alert_id},
                success=False,
                error_message=str(e)[:500],
            )
            return None

    def _save_to_database(
        self,
        agent_result: dict,
        alert_data: dict,
        jira_ticket_id: Optional[str],
    ) -> Optional[int]:
        """Save incident to PostgreSQL."""
        try:
            incident_id = save_incident(
                db=self._db,
                agent_result=agent_result,
                alert_data=alert_data,
                jira_ticket_id=jira_ticket_id,
            )
            return incident_id
        except Exception as e:
            logger.error(
                "db.save_failed",
                alert_id=agent_result.get("alert_id"),
                error=str(e),
            )
            return None

    def _update_redis_with_ticket(self, alert_id: str, jira_ticket_id: str) -> None:
        """Update the cached alert in Redis with the Jira ticket ID."""
        try:
            redis = get_redis_client()
            redis.update_alert_status(
                alert_id,
                "RESOLVED",
                jira_ticket_id=jira_ticket_id,
            )
            logger.debug(
                "redis.alert_updated_with_ticket",
                alert_id=alert_id,
                jira_ticket_id=jira_ticket_id,
            )
        except Exception as e:
            logger.warning(
                "redis.alert_update_failed",
                alert_id=alert_id,
                error=str(e),
            )
