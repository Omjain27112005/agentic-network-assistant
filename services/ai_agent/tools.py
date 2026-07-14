"""
Agent Tools — functions the AI Agent can call during the ReAct loop.

Two things defined here per tool:
1. Python function — actual implementation that reads from Redis
2. JSON Schema — tells Groq what the tool does and what args it takes

Tool Calling Flow:
    Agent sees alert → needs more data
    Agent calls: get_device_metrics("R1")
    We execute the Python function → fetch from Redis
    We send result back to Agent as a "tool" message
    Agent now has the data → reasons further → maybe calls another tool
    Agent finally produces root cause conclusion

Available Tools:
- get_device_metrics(device_id)        → current metrics for one device
- get_device_history(device_id, mins)  → last N minutes of metrics
- get_neighboring_devices(device_id)   → list of directly connected devices
- get_all_active_alerts()              → all currently open alerts
- get_network_health_score()           → overall network health 0-100
"""
import json
from typing import Any, Dict, List, Optional

import structlog

from shared.redis_client import get_redis_client
from services.network_simulator.devices import DEVICE_MAP

logger = structlog.get_logger(__name__)


# -----------------------------------------------
# Tool Implementation Functions
# -----------------------------------------------

def get_device_metrics(device_id: str) -> str:
    """
    Fetch current metrics for a specific device from Redis.

    Returns JSON string with all metric fields, or error message.
    """
    try:
        redis = get_redis_client()
        metrics = redis.get_device_metrics(device_id)

        if not metrics:
            return json.dumps({
                "error": f"No metrics found for device {device_id}. "
                         f"Device may be down or not yet reporting.",
                "device_id": device_id,
            })

        # Add state for context
        state = redis.get_device_state(device_id) or "UNKNOWN"
        metrics["state"] = state

        logger.debug("tool.get_device_metrics", device_id=device_id, state=state)
        return json.dumps(metrics, indent=2)

    except Exception as e:
        logger.error("tool.get_device_metrics.failed", device_id=device_id, error=str(e))
        return json.dumps({"error": f"Failed to fetch metrics for {device_id}: {str(e)}"})


def get_device_history(device_id: str, minutes: int = 10) -> str:
    """
    Fetch recent metric history for a device from Redis time-series.
    Helps detect trends: is latency steadily rising or a sudden spike?

    Returns JSON array of timestamped snapshots.
    """
    try:
        redis = get_redis_client()

        # Each entry covers 5s interval. minutes*60/5 = entries needed
        limit = min((minutes * 60) // 5, 72)  # Cap at 72 (max stored)
        history_raw = redis.get_device_history(device_id, limit=limit)

        if not history_raw:
            return json.dumps({
                "device_id": device_id,
                "minutes_requested": minutes,
                "entries_found": 0,
                "history": [],
                "note": "No history available — device may have recently started",
            })

        history = [json.loads(entry) for entry in history_raw]

        logger.debug(
            "tool.get_device_history",
            device_id=device_id,
            minutes=minutes,
            entries=len(history),
        )

        return json.dumps({
            "device_id": device_id,
            "minutes_requested": minutes,
            "entries_found": len(history),
            "history": history,
        }, indent=2)

    except Exception as e:
        logger.error("tool.get_device_history.failed", device_id=device_id, error=str(e))
        return json.dumps({"error": f"Failed to fetch history for {device_id}: {str(e)}"})


def get_neighboring_devices(device_id: str) -> str:
    """
    Get the list of devices directly connected to the given device.
    Used to check if neighbors are also affected (cascade detection).

    Returns JSON with neighbor device IDs and their current states.
    """
    try:
        device = DEVICE_MAP.get(device_id)
        if not device:
            return json.dumps({
                "error": f"Device {device_id} not found in topology",
                "device_id": device_id,
            })

        redis = get_redis_client()
        neighbors_info = []

        for neighbor_id in device.neighbors:
            state = redis.get_device_state(neighbor_id) or "UNKNOWN"
            metrics = redis.get_device_metrics(neighbor_id)

            neighbor_data: Dict[str, Any] = {
                "device_id": neighbor_id,
                "state": state,
            }
            if metrics:
                neighbor_data["latency_ms"] = metrics.get("latency_ms", "N/A")
                neighbor_data["packet_loss_percent"] = metrics.get("packet_loss_percent", "N/A")
                neighbor_data["cpu_percent"] = metrics.get("cpu_percent", "N/A")

            neighbors_info.append(neighbor_data)

        logger.debug(
            "tool.get_neighboring_devices",
            device_id=device_id,
            neighbor_count=len(neighbors_info),
        )

        return json.dumps({
            "device_id": device_id,
            "device_type": device.device_type if isinstance(device.device_type, str) else device.device_type.value,
            "neighbor_count": len(neighbors_info),
            "neighbors": neighbors_info,
        }, indent=2)

    except Exception as e:
        logger.error("tool.get_neighboring_devices.failed", device_id=device_id, error=str(e))
        return json.dumps({"error": f"Failed to get neighbors for {device_id}: {str(e)}"})


def get_all_active_alerts() -> str:
    """
    Fetch all currently open/investigating alerts from Redis.
    Helps agent understand the full scope: is this one isolated issue
    or part of a larger pattern?

    Returns JSON array of all active alerts.
    """
    try:
        redis = get_redis_client()
        alerts = redis.get_all_active_alerts()

        if not alerts:
            return json.dumps({
                "active_alert_count": 0,
                "alerts": [],
                "note": "No active alerts at this time",
            })

        # Sort by severity for clarity: EMERGENCY first, then CRITICAL, etc.
        severity_order = {"EMERGENCY": 0, "CRITICAL": 1, "WARNING": 2, "INFO": 3}
        alerts.sort(key=lambda a: severity_order.get(a.get("severity", "INFO"), 4))

        logger.debug("tool.get_all_active_alerts", count=len(alerts))

        return json.dumps({
            "active_alert_count": len(alerts),
            "alerts": alerts,
        }, indent=2)

    except Exception as e:
        logger.error("tool.get_all_active_alerts.failed", error=str(e))
        return json.dumps({"error": f"Failed to fetch active alerts: {str(e)}"})


def get_network_health_score() -> str:
    """
    Get the overall network health score (0-100).
    Provides context on whether this is an isolated incident
    or a broad network degradation event.
    """
    try:
        redis = get_redis_client()
        score = redis.get_health_score()

        # Classify score
        if score >= 90:
            health_status = "HEALTHY"
            interpretation = "Network is operating normally. This may be an isolated incident."
        elif score >= 70:
            health_status = "DEGRADED"
            interpretation = "Multiple devices showing issues. Possible widespread problem."
        elif score >= 50:
            health_status = "CRITICAL"
            interpretation = "Significant portion of network is impacted. Escalation likely needed."
        else:
            health_status = "EMERGENCY"
            interpretation = "Severe network degradation. Multiple devices down or failing."

        logger.debug("tool.get_network_health_score", score=score, status=health_status)

        return json.dumps({
            "health_score": score,
            "health_status": health_status,
            "interpretation": interpretation,
            "scale": "0 = complete outage, 100 = fully healthy",
        }, indent=2)

    except Exception as e:
        logger.error("tool.get_network_health_score.failed", error=str(e))
        return json.dumps({"error": f"Failed to fetch health score: {str(e)}"})


# -----------------------------------------------
# Tool Dispatcher
# -----------------------------------------------

# Maps tool name → Python function
TOOL_FUNCTION_MAP = {
    "get_device_metrics": lambda args: get_device_metrics(args["device_id"]),
    "get_device_history": lambda args: get_device_history(
        args["device_id"],
        args.get("minutes", 10),
    ),
    "get_neighboring_devices": lambda args: get_neighboring_devices(args["device_id"]),
    "get_all_active_alerts": lambda args: get_all_active_alerts(),
    "get_network_health_score": lambda args: get_network_health_score(),
}


def execute_tool(tool_name: str, tool_args: Dict[str, Any]) -> str:
    """
    Execute a tool by name with given arguments.

    Returns:
        JSON string result (always a string — Groq requires tool results as strings)
    """
    if tool_name not in TOOL_FUNCTION_MAP:
        logger.error("tool.unknown", tool_name=tool_name)
        return json.dumps({"error": f"Unknown tool: {tool_name}"})

    try:
        logger.info("tool.executing", tool_name=tool_name, args=tool_args)
        result = TOOL_FUNCTION_MAP[tool_name](tool_args)
        logger.info("tool.executed", tool_name=tool_name, result_length=len(result))
        return result
    except Exception as e:
        logger.error("tool.execution_failed", tool_name=tool_name, error=str(e))
        return json.dumps({"error": f"Tool {tool_name} failed: {str(e)}"})


# -----------------------------------------------
# Groq Tool Definitions (JSON Schema)
# Tells the LLM what tools are available and how to call them
# -----------------------------------------------

GROQ_TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "get_device_metrics",
            "description": (
                "Fetch the current real-time metrics for a specific network device. "
                "Returns latency, packet loss, CPU, memory, bandwidth utilization, "
                "interface errors, uptime, and operational status."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "device_id": {
                        "type": "string",
                        "description": "The device identifier. Valid values: R1, R2, R3, S1, S2, S3, S4, AP1, AP2, AP3",
                    }
                },
                "required": ["device_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_device_history",
            "description": (
                "Fetch historical metric snapshots for a device over the last N minutes. "
                "Use this to detect trends — is a metric steadily worsening, or was it a sudden spike? "
                "Useful for distinguishing intermittent failures from persistent issues."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "device_id": {
                        "type": "string",
                        "description": "The device identifier (R1, R2, R3, S1, S2, S3, S4, AP1, AP2, AP3)",
                    },
                    "minutes": {
                        "type": "integer",
                        "description": "How many minutes of history to retrieve. Min: 1, Max: 6. Default: 10.",
                        "default": 10,
                    },
                },
                "required": ["device_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_neighboring_devices",
            "description": (
                "Get the list of devices directly connected to a given device in the network topology. "
                "Also returns current state and key metrics for each neighbor. "
                "Use this to check if a failure is cascading to connected devices, "
                "which helps identify whether the root cause is upstream or on the device itself."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "device_id": {
                        "type": "string",
                        "description": "The device identifier to find neighbors for",
                    }
                },
                "required": ["device_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_all_active_alerts",
            "description": (
                "Fetch all currently active (open or investigating) alerts across the entire network. "
                "Use this to understand the full scope of the incident — "
                "whether it is isolated to one device or part of a broader outage pattern."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_network_health_score",
            "description": (
                "Get the overall network health score on a scale of 0-100. "
                "100 = fully healthy, 0 = complete network outage. "
                "Use this for situational awareness about the severity of the overall situation."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
]
