"""Devices router — live device metrics and status endpoints."""
from typing import List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from shared.redis_client import get_redis_client
from services.network_simulator.devices import DEVICES, DEVICE_MAP

router = APIRouter()


class DeviceMetricsResponse(BaseModel):
    device_id: str
    device_type: str
    location: str
    ip_address: str
    neighbors: List[str]
    status: Optional[str] = "UNKNOWN"
    latency_ms: Optional[float] = None
    packet_loss_percent: Optional[float] = None
    cpu_percent: Optional[float] = None
    memory_percent: Optional[float] = None
    bandwidth_utilization_percent: Optional[float] = None
    interface_errors_per_min: Optional[int] = None
    uptime_seconds: Optional[int] = None
    timestamp: Optional[str] = None


@router.get("/devices", response_model=List[DeviceMetricsResponse])
async def get_all_devices():
    """
    Get all devices with their latest cached metrics from Redis.
    Returns the full topology with live status.
    """
    redis = get_redis_client()
    result = []

    for device in DEVICES:
        device_type = device.device_type if isinstance(device.device_type, str) else device.device_type.value
        row = DeviceMetricsResponse(
            device_id=device.device_id,
            device_type=device_type,
            location=device.location,
            ip_address=device.ip_address,
            neighbors=device.neighbors,
        )

        # Enrich with live metrics from Redis
        metrics = redis.get_device_metrics(device.device_id)
        state = redis.get_device_state(device.device_id)
        row.status = state or "UNKNOWN"

        if metrics:
            row.latency_ms = float(metrics.get("latency_ms", 0))
            row.packet_loss_percent = float(metrics.get("packet_loss_percent", 0))
            row.cpu_percent = float(metrics.get("cpu_percent", 0))
            row.memory_percent = float(metrics.get("memory_percent", 0))
            row.bandwidth_utilization_percent = float(metrics.get("bandwidth_utilization_percent", 0))
            row.interface_errors_per_min = int(float(metrics.get("interface_errors_per_min", 0)))
            row.uptime_seconds = int(float(metrics.get("uptime_seconds", 0)))
            row.timestamp = metrics.get("timestamp")

        result.append(row)

    return result


@router.get("/devices/{device_id}", response_model=DeviceMetricsResponse)
async def get_device(device_id: str):
    """Get metrics for a specific device by ID."""
    device = DEVICE_MAP.get(device_id)
    if not device:
        raise HTTPException(status_code=404, detail=f"Device {device_id} not found")

    redis = get_redis_client()
    device_type = device.device_type if isinstance(device.device_type, str) else device.device_type.value
    row = DeviceMetricsResponse(
        device_id=device.device_id,
        device_type=device_type,
        location=device.location,
        ip_address=device.ip_address,
        neighbors=device.neighbors,
        status=redis.get_device_state(device_id) or "UNKNOWN",
    )

    metrics = redis.get_device_metrics(device_id)
    if metrics:
        row.latency_ms = float(metrics.get("latency_ms", 0))
        row.packet_loss_percent = float(metrics.get("packet_loss_percent", 0))
        row.cpu_percent = float(metrics.get("cpu_percent", 0))
        row.memory_percent = float(metrics.get("memory_percent", 0))
        row.bandwidth_utilization_percent = float(metrics.get("bandwidth_utilization_percent", 0))
        row.interface_errors_per_min = int(float(metrics.get("interface_errors_per_min", 0)))
        row.uptime_seconds = int(float(metrics.get("uptime_seconds", 0)))
        row.timestamp = metrics.get("timestamp")

    return row


@router.get("/devices/{device_id}/history")
async def get_device_history(device_id: str, minutes: int = 6):
    """Get metric history time-series for a device (max 6 minutes)."""
    import json
    device = DEVICE_MAP.get(device_id)
    if not device:
        raise HTTPException(status_code=404, detail=f"Device {device_id} not found")

    redis = get_redis_client()
    limit = min((minutes * 60) // 5, 72)
    raw = redis.get_device_history(device_id, limit=limit)
    history = [json.loads(entry) for entry in raw]

    return {"device_id": device_id, "minutes": minutes, "count": len(history), "history": history}


@router.get("/network/health")
async def get_network_health():
    """Get overall network health score and per-device status summary."""
    redis = get_redis_client()
    health_score = redis.get_health_score()

    device_states = {}
    for device in DEVICES:
        state = redis.get_device_state(device.device_id) or "UNKNOWN"
        device_states[device.device_id] = state

    down_count = sum(1 for s in device_states.values() if s == "DOWN")
    degraded_count = sum(1 for s in device_states.values() if s == "DEGRADED")
    up_count = sum(1 for s in device_states.values() if s == "UP")

    return {
        "health_score": health_score,
        "total_devices": len(DEVICES),
        "up": up_count,
        "degraded": degraded_count,
        "down": down_count,
        "device_states": device_states,
    }
