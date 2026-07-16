"""
WebSocket router — real-time live data streaming to React frontend.

Broadcasts two types of events every 3 seconds:
1. metrics_update — latest device metrics for all 10 devices
2. alerts_update  — current active alerts

React frontend connects to ws://localhost:8000/ws/live
and updates its Zustand store on every message.

Connection Manager:
- Tracks all active WebSocket connections
- Broadcasts to all connected clients simultaneously
- Cleans up disconnected clients automatically
"""
import json
import asyncio
from typing import Set

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from shared.redis_client import get_redis_client
from services.network_simulator.devices import DEVICES

router = APIRouter()
logger = structlog.get_logger(__name__)

BROADCAST_INTERVAL_SECONDS = 3  # Push update every 3 seconds


class ConnectionManager:
    """Manages all active WebSocket connections."""

    def __init__(self):
        self._active: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._active.add(websocket)
        logger.info("websocket.client_connected", total=len(self._active))

    def disconnect(self, websocket: WebSocket) -> None:
        self._active.discard(websocket)
        logger.info("websocket.client_disconnected", total=len(self._active))

    async def broadcast(self, message: dict) -> None:
        """Send message to all connected clients. Remove dead connections."""
        dead = set()
        payload = json.dumps(message)

        for ws in self._active:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.add(ws)

        # Cleanup dead connections
        for ws in dead:
            self._active.discard(ws)


manager = ConnectionManager()


def _build_live_snapshot() -> dict:
    """Read current state from Redis and build a snapshot dict."""
    redis = get_redis_client()

    # Device metrics
    devices_data = []
    for device in DEVICES:
        device_type = device.device_type if isinstance(device.device_type, str) else device.device_type.value
        d = {
            "device_id": device.device_id,
            "device_type": device_type,
            "location": device.location,
            "status": redis.get_device_state(device.device_id) or "UNKNOWN",
        }
        metrics = redis.get_device_metrics(device.device_id)
        if metrics:
            d["latency_ms"] = float(metrics.get("latency_ms", 0))
            d["cpu_percent"] = float(metrics.get("cpu_percent", 0))
            d["memory_percent"] = float(metrics.get("memory_percent", 0))
            d["packet_loss_percent"] = float(metrics.get("packet_loss_percent", 0))
            d["bandwidth_utilization_percent"] = float(metrics.get("bandwidth_utilization_percent", 0))
            d["timestamp"] = metrics.get("timestamp", "")
        devices_data.append(d)

    # Active alerts
    raw_alerts = redis.get_all_active_alerts()
    alerts_data = []
    for a in raw_alerts[:20]:  # Cap at 20 for bandwidth
        try:
            alerts_data.append({
                "alert_id": a.get("alert_id", ""),
                "device_id": a.get("device_id", ""),
                "alert_type": a.get("alert_type", ""),
                "severity": a.get("severity", ""),
                "threshold_breached": a.get("threshold_breached", ""),
                "timestamp": a.get("timestamp", ""),
                "status": a.get("status", "OPEN"),
            })
        except Exception:
            continue

    # Health score
    health_score = redis.get_health_score()

    return {
        "type": "live_update",
        "health_score": health_score,
        "devices": devices_data,
        "alerts": alerts_data,
        "alert_count": len(raw_alerts),
    }


@router.websocket("/live")
async def websocket_live(websocket: WebSocket):
    """
    WebSocket endpoint for live dashboard updates.

    Client connects once, server pushes data every 3 seconds.
    Client doesn't need to send anything — this is push-only.

    Message format:
    {
      "type": "live_update",
      "health_score": 85.0,
      "devices": [...],
      "alerts": [...],
      "alert_count": 3
    }
    """
    await manager.connect(websocket)

    try:
        while True:
            # Build snapshot from Redis
            snapshot = _build_live_snapshot()

            # Push to this client
            await websocket.send_text(json.dumps(snapshot))

            # Wait for next cycle
            await asyncio.sleep(BROADCAST_INTERVAL_SECONDS)

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error("websocket.error", error=str(e))
        manager.disconnect(websocket)
