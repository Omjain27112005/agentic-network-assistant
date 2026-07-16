"""
Jira Client — production-grade wrapper for Jira REST API v3.

Responsibilities:
- Create incident tickets in Jira automatically
- Add investigation details as ticket description
- Set priority, labels, and component based on severity
- Handle auth errors, network errors, and rate limits gracefully

Jira API Auth: Basic Auth with email + API token (not password)
Get your token: https://id.atlassian.com/manage-profile/security/api-tokens

Production features:
- Session reuse (keep-alive connections — faster than creating new per request)
- Retry with exponential backoff on 429 (rate limit) and 5xx errors
- Full ticket URL returned for storage in PostgreSQL
- Dry-run mode: if Jira not configured, logs what would have been created
"""
import time
import logging
import base64
from typing import Optional, Dict, Any

import httpx
import structlog

logger = structlog.get_logger(__name__)


# Jira priority mapping from our severity levels
SEVERITY_TO_JIRA_PRIORITY = {
    "EMERGENCY": "Highest",
    "CRITICAL":  "High",
    "WARNING":   "Medium",
    "INFO":      "Low",
}

# Jira label mapping from alert types
ALERT_TYPE_TO_LABEL = {
    "HIGH_LATENCY":           "latency",
    "PACKET_LOSS":            "packet-loss",
    "DEVICE_DOWN":            "device-down",
    "HIGH_CPU":               "cpu-spike",
    "HIGH_MEMORY":            "memory-pressure",
    "HIGH_INTERFACE_ERRORS":  "interface-errors",
    "BANDWIDTH_SATURATION":   "bandwidth",
    "CASCADING_FAILURE":      "cascading-failure",
}


class JiraClient:
    """
    Async-friendly Jira REST API v3 client using httpx.

    Usage:
        client = JiraClient(base_url, email, api_token, project_key)
        ticket = client.create_incident_ticket(agent_result, alert_data)
        print(ticket.ticket_id)   # "NET-1042"
        print(ticket.ticket_url)  # "https://your-org.atlassian.net/browse/NET-1042"
    """

    MAX_RETRIES = 3
    BASE_BACKOFF = 2.0
    REQUEST_TIMEOUT = 15.0  # seconds

    def __init__(
        self,
        base_url: str,
        email: str,
        api_token: str,
        project_key: str,
    ):
        self._base_url = base_url.rstrip("/")
        self._project_key = project_key
        self._configured = bool(base_url and email and api_token)

        if not self._configured:
            logger.warning(
                "jira_client.not_configured",
                reason="JIRA_BASE_URL, JIRA_EMAIL or JIRA_API_TOKEN missing — running in dry-run mode",
            )
            return

        # Basic Auth header: base64("email:api_token")
        credentials = f"{email}:{api_token}"
        encoded = base64.b64encode(credentials.encode()).decode()

        self._headers = {
            "Authorization": f"Basic {encoded}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        # Reuse HTTP session — persistent connection pool
        self._client = httpx.Client(
            base_url=self._base_url,
            headers=self._headers,
            timeout=self.REQUEST_TIMEOUT,
            follow_redirects=True,
        )

        logger.info("jira_client.initialized", project_key=project_key, base_url=base_url)

    def create_incident_ticket(
        self,
        agent_result: Dict[str, Any],
        alert_data: Dict[str, Any],
    ) -> Optional[Dict[str, str]]:
        """
        Create a Jira incident ticket from an AI Agent investigation result.

        Args:
            agent_result: AgentResult dict from Kafka network.actions
            alert_data: Original alert dict for context

        Returns:
            Dict with ticket_id and ticket_url, or None if creation failed
        """
        if not self._configured:
            # Dry-run — log what would have been created
            dry_run_id = f"{self._project_key}-DRY-{int(time.time())}"
            logger.info(
                "jira_client.dry_run_ticket",
                ticket_id=dry_run_id,
                device_id=agent_result.get("device_id"),
                root_cause=agent_result.get("root_cause", "")[:100],
                severity=alert_data.get("severity"),
            )
            return {
                "ticket_id": dry_run_id,
                "ticket_url": f"https://your-org.atlassian.net/browse/{dry_run_id}",
                "dry_run": "true",
            }

        severity = alert_data.get("severity", "CRITICAL")
        alert_type = alert_data.get("alert_type", "UNKNOWN")
        device_id = agent_result.get("device_id", "UNKNOWN")
        root_cause = agent_result.get("root_cause", "Root cause undetermined")
        confidence = agent_result.get("confidence_score", 0.0)
        affected_devices = agent_result.get("affected_devices", [device_id])
        immediate_action = agent_result.get("immediate_action", "Manual investigation required")
        investigation_summary = agent_result.get("investigation_summary", "")
        is_cascading = agent_result.get("is_cascading", False)
        iterations = agent_result.get("iterations_used", 0)
        tool_calls = agent_result.get("tool_calls_made", 0)
        duration = agent_result.get("duration_seconds", 0.0)
        alert_id = alert_data.get("alert_id", "UNKNOWN")

        # Build the Jira ticket summary (title)
        cascade_prefix = "[CASCADE] " if is_cascading else ""
        summary = (
            f"{cascade_prefix}[{severity}] {alert_type} on {device_id} "
            f"— {', '.join(affected_devices[:3])}"
        )

        # Build the description using Atlassian Document Format (ADF)
        # ADF is the rich-text format Jira uses for descriptions
        description_text = self._build_description(
            alert_id=alert_id,
            device_id=device_id,
            alert_type=alert_type,
            severity=severity,
            root_cause=root_cause,
            confidence=confidence,
            affected_devices=affected_devices,
            is_cascading=is_cascading,
            immediate_action=immediate_action,
            investigation_summary=investigation_summary,
            threshold_breached=alert_data.get("threshold_breached", ""),
            iterations=iterations,
            tool_calls=tool_calls,
            duration=duration,
        )

        # Build Jira API payload
        payload = {
            "fields": {
                "project": {"key": self._project_key},
                "summary": summary[:255],  # Jira summary max 255 chars
                "issuetype": {"name": "Bug"},
                "priority": {"name": SEVERITY_TO_JIRA_PRIORITY.get(severity, "High")},
                "description": {
                    "type": "doc",
                    "version": 1,
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [{"type": "text", "text": description_text}],
                        }
                    ],
                },
                "labels": [
                    "network-incident",
                    "auto-generated",
                    ALERT_TYPE_TO_LABEL.get(alert_type, "network"),
                    f"device-{device_id.lower()}",
                ],
            }
        }

        # Create ticket with retry
        return self._create_issue_with_retry(payload)

    def close(self) -> None:
        """Close the HTTP client connection pool."""
        if self._configured and hasattr(self, "_client"):
            self._client.close()
            logger.info("jira_client.closed")

    # -----------------------------------------------
    # Private Helpers
    # -----------------------------------------------

    def _create_issue_with_retry(self, payload: Dict) -> Optional[Dict[str, str]]:
        """POST /rest/api/3/issue with exponential backoff retry."""
        last_error = None

        for attempt in range(self.MAX_RETRIES + 1):
            try:
                response = self._client.post(
                    "/rest/api/3/issue",
                    json=payload,
                )

                if response.status_code == 201:
                    data = response.json()
                    ticket_id = data["key"]
                    ticket_url = f"{self._base_url}/browse/{ticket_id}"

                    logger.info(
                        "jira.ticket_created",
                        ticket_id=ticket_id,
                        ticket_url=ticket_url,
                        attempt=attempt + 1,
                    )
                    return {"ticket_id": ticket_id, "ticket_url": ticket_url}

                elif response.status_code == 429:
                    # Rate limit — respect Retry-After header if present
                    retry_after = int(response.headers.get("Retry-After", self.BASE_BACKOFF ** (attempt + 1)))
                    logger.warning("jira.rate_limited", retry_after=retry_after, attempt=attempt + 1)
                    time.sleep(retry_after)
                    last_error = f"Rate limited (429)"

                elif response.status_code >= 500:
                    wait = self.BASE_BACKOFF ** (attempt + 1)
                    logger.warning(
                        "jira.server_error",
                        status=response.status_code,
                        attempt=attempt + 1,
                        wait=wait,
                    )
                    time.sleep(wait)
                    last_error = f"Server error {response.status_code}: {response.text[:200]}"

                else:
                    # 4xx client error — not retryable
                    logger.error(
                        "jira.client_error",
                        status=response.status_code,
                        response=response.text[:300],
                    )
                    return None

            except httpx.TimeoutException as e:
                wait = self.BASE_BACKOFF ** (attempt + 1)
                logger.warning("jira.timeout", attempt=attempt + 1, wait=wait)
                time.sleep(wait)
                last_error = str(e)

            except httpx.RequestError as e:
                wait = self.BASE_BACKOFF ** (attempt + 1)
                logger.warning("jira.connection_error", error=str(e), attempt=attempt + 1, wait=wait)
                time.sleep(wait)
                last_error = str(e)

        logger.error("jira.max_retries_exhausted", last_error=last_error)
        return None

    def _build_description(self, **kwargs) -> str:
        """Build a human-readable Jira ticket description."""
        affected = ", ".join(kwargs.get("affected_devices", []))
        cascade_note = "⚠️ YES — Multiple devices affected" if kwargs.get("is_cascading") else "No"

        return f"""
🤖 AUTO-GENERATED BY AI NETWORK AGENT
════════════════════════════════════════

📋 INCIDENT SUMMARY
Alert ID:           {kwargs.get('alert_id')}
Device:             {kwargs.get('device_id')}
Alert Type:         {kwargs.get('alert_type')}
Severity:           {kwargs.get('severity')}
Threshold Breached: {kwargs.get('threshold_breached')}
Affected Devices:   {affected}
Cascading Failure:  {cascade_note}

🧠 AI ROOT CAUSE ANALYSIS
{kwargs.get('root_cause')}

Confidence Score: {round(float(kwargs.get('confidence', 0)) * 100)}%

🔍 INVESTIGATION SUMMARY
{kwargs.get('investigation_summary')}

⚡ IMMEDIATE ACTION REQUIRED
{kwargs.get('immediate_action')}

📊 AGENT METADATA
Iterations Used:  {kwargs.get('iterations')}
Tool Calls Made:  {kwargs.get('tool_calls')}
Analysis Duration: {kwargs.get('duration')}s

════════════════════════════════════════
This ticket was automatically created by the Agentic Network Assistant.
Please update this ticket with your findings and close when resolved.
""".strip()
