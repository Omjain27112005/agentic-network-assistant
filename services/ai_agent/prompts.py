"""
Prompts — system prompt and context builders for the AI Agent.

Prompt Engineering Principles Applied:
1. Clear role definition — agent knows exactly what it is
2. Structured reasoning steps — guides ReAct behaviour
3. Topology context — agent knows the network layout upfront
4. Output format enforcement — agent must produce structured JSON conclusion
5. Grounded instructions — agent only uses tool data, no hallucination

Why does prompt quality matter?
A vague prompt produces vague answers.
A precise prompt with clear steps produces consistent, actionable output.
We want the agent to always produce: root_cause, confidence, recommendation.
"""

# -----------------------------------------------
# Network Topology Description
# Embedded in system prompt so agent understands device relationships
# -----------------------------------------------
TOPOLOGY_DESCRIPTION = """
Network Topology:
- Core Routers: R1, R2 (DataCenter-Core), R3 (DataCenter-Edge)
- Distribution Switches: S1 (Floor-1), S2 (Floor-2), S3 (Floor-3), S4 (DataCenter-Access)
- Access Points: AP1 (Floor-1-Zone-A), AP2 (Floor-2-Zone-A), AP3 (Floor-3-Zone-A)

Connectivity:
  R3 ──── R1 ──── R2
          │  ╲   / │
          S1  R3  S3
          │         │
          AP1      AP3
          
  R1 → S1 → AP1 (Floor-1 path)
  R1 → S2 → AP2 (Floor-2 path)
  R2 → S3 → AP3 (Floor-3 path)
  R2 → S4 (DataCenter access)
  R1 ↔ R2 ↔ R3 (Core interconnect)

Normal Metric Ranges:
  Routers:      latency 8-25ms,  packet_loss 0-0.3%,  cpu 20-60%
  Switches:     latency 2-10ms,  packet_loss 0-0.1%,  cpu 10-40%
  AccessPoints: latency 5-20ms,  packet_loss 0-0.5%,  cpu 5-35%
"""


# -----------------------------------------------
# System Prompt — defines the agent's role and reasoning process
# -----------------------------------------------
SYSTEM_PROMPT = f"""You are an expert AI network operations engineer named Marvis.
Your job is to investigate network incidents and determine the root cause with precision.

{TOPOLOGY_DESCRIPTION}

## Your Investigation Process (ReAct)
You MUST follow these steps in order:

1. OBSERVE: Read the alert details carefully.
2. GATHER DATA: Use the available tools to collect evidence.
   - Always check the affected device's current metrics
   - Always check the device's history to determine if this is sudden or gradual
   - Always check neighboring devices to detect cascading failures
   - Check all active alerts to understand the full scope
3. REASON: Analyze the collected evidence systematically.
   - What metrics are abnormal? By how much?
   - Are neighbors affected? If yes → upstream or shared infrastructure issue
   - Is the issue sudden or gradual? Sudden = failure/attack. Gradual = degradation/leak
   - What is the most likely root cause?
4. CONCLUDE: Produce a structured JSON conclusion.

## Rules
- NEVER guess without data. Use tools to gather evidence first.
- If a device is DOWN, check its neighbors first — the root cause may be upstream.
- Low confidence (<60%) means you need more data — call more tools.
- Cascading failures (multiple devices in same path) suggest a shared upstream issue.
- A single device with high CPU but normal neighbors → local issue (process, config, DDoS).

## Output Format
When you have completed your investigation, output a JSON block wrapped in ```json ... ``` tags:

```json
{{
  "root_cause": "Clear, specific description of what caused this alert",
  "confidence_score": 0.85,
  "affected_devices": ["R1", "S1"],
  "is_cascading": false,
  "severity_assessment": "CRITICAL",
  "immediate_action": "Specific action to take right now",
  "investigation_summary": "2-3 sentence summary of your reasoning process"
}}
```

confidence_score must be between 0.0 and 1.0.
Do not include any text after the JSON block.
"""


# -----------------------------------------------
# Alert Context Builder
# Formats the alert into a clear investigation prompt
# -----------------------------------------------

def build_alert_context(alert_data: dict) -> str:
    """
    Build the initial user message from alert data.
    This is what the agent sees first — the incident trigger.

    Args:
        alert_data: Dict with alert fields (from Kafka/Redis)

    Returns:
        Formatted string describing the incident to investigate
    """
    device_id = alert_data.get("device_id", "UNKNOWN")
    alert_type = alert_data.get("alert_type", "UNKNOWN")
    severity = alert_data.get("severity", "UNKNOWN")
    threshold_breached = alert_data.get("threshold_breached", "No details available")
    alert_id = alert_data.get("alert_id", "UNKNOWN")
    timestamp = alert_data.get("timestamp", "UNKNOWN")

    return f"""## INCIDENT ALERT — Requires Investigation

Alert ID:           {alert_id}
Severity:           {severity}
Device:             {device_id}
Alert Type:         {alert_type}
Threshold Breached: {threshold_breached}
Detected At:        {timestamp}

Please investigate this incident using the available tools.
Start by fetching the current metrics for {device_id}, then check its history and neighbors.
Conclude with a structured JSON diagnosis.
"""


def build_chat_context(user_question: str, network_snapshot: dict) -> str:
    """
    Build context for the conversational chat interface.
    Gives the LLM a snapshot of current network state before answering.

    Args:
        user_question: The engineer's natural language question
        network_snapshot: Dict with current alerts, health score, device states

    Returns:
        Formatted prompt with current network state + user question
    """
    active_alerts = network_snapshot.get("active_alerts", [])
    health_score = network_snapshot.get("health_score", 100.0)
    devices_down = [
        d for d, state in network_snapshot.get("device_states", {}).items()
        if state == "DOWN"
    ]
    devices_degraded = [
        d for d, state in network_snapshot.get("device_states", {}).items()
        if state == "DEGRADED"
    ]

    alert_summary = ""
    if active_alerts:
        alert_lines = []
        for a in active_alerts[:5]:  # Show top 5 alerts max
            alert_lines.append(
                f"  - [{a.get('severity')}] {a.get('device_id')} — "
                f"{a.get('alert_type')}: {a.get('threshold_breached', '')}"
            )
        alert_summary = "Active Alerts:\n" + "\n".join(alert_lines)
    else:
        alert_summary = "Active Alerts: None — network appears healthy"

    return f"""## Current Network Status (as of now)
Network Health Score: {health_score}/100
Devices DOWN: {', '.join(devices_down) if devices_down else 'None'}
Devices DEGRADED: {', '.join(devices_degraded) if devices_degraded else 'None'}

{alert_summary}

## Engineer's Question
{user_question}

Please answer based on the current network status above.
Be specific and actionable. Reference device IDs and metric values where relevant.
"""
