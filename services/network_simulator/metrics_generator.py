"""
Metrics Generator — produces realistic network metrics using normal distribution.

Why normal distribution?
Real network metrics don't jump randomly between min and max.
They cluster around a typical value with small variations.
Example: Router latency is usually ~15ms, occasionally 10ms or 22ms — not random between 8-25ms.

Normal distribution captures this "clustering around mean" behavior perfectly.
"""
import random
import time
from datetime import datetime, timezone
from typing import Dict

from shared.models.device import Device, DeviceStatus
from shared.models.metric import NetworkMetric
from services.network_simulator.devices import DEVICE_NORMAL_RANGES


def generate_metric(device: Device, uptime_start: float) -> NetworkMetric:
    """
    Generate one realistic metric snapshot for a device.

    Uses normal distribution:
        mean  = midpoint of normal range
        sigma = (max - min) / 6   (so 99.7% of values fall within range)

    Args:
        device: The device to generate metrics for
        uptime_start: Unix timestamp when this device was "started"

    Returns:
        NetworkMetric with realistic values
    """
    device_type = device.device_type.value if hasattr(device.device_type, 'value') else device.device_type
    ranges = DEVICE_NORMAL_RANGES[device_type]

    def normal_value(min_val: float, max_val: float) -> float:
        """Sample from normal distribution clamped to [min, max]."""
        mean = (min_val + max_val) / 2
        sigma = (max_val - min_val) / 6
        value = random.gauss(mean, sigma)
        return round(max(min_val, min(max_val, value)), 2)

    # Generate all metrics
    latency = normal_value(*ranges["latency_ms"])
    packet_loss = normal_value(*ranges["packet_loss_percent"])
    bandwidth = normal_value(*ranges["bandwidth_utilization_percent"])
    cpu = normal_value(*ranges["cpu_percent"])
    memory = normal_value(*ranges["memory_percent"])

    # Interface errors — discrete value (integer)
    err_min, err_max = ranges["interface_errors_per_min"]
    errors = int(normal_value(err_min, err_max))

    # Uptime in seconds since device "started"
    uptime = int(time.time() - uptime_start)

    # Determine status from current metrics
    status = _compute_status(latency, packet_loss, cpu, device_type)

    return NetworkMetric(
        device_id=device.device_id,
        timestamp=datetime.now(timezone.utc),
        latency_ms=latency,
        packet_loss_percent=packet_loss,
        bandwidth_utilization_percent=bandwidth,
        cpu_percent=cpu,
        memory_percent=memory,
        interface_errors_per_min=errors,
        uptime_seconds=uptime,
        status=status,
    )


def _compute_status(
    latency: float,
    packet_loss: float,
    cpu: float,
    device_type: str,
) -> DeviceStatus:
    """
    Determine device health status from current metric values.

    Rules:
    - DEGRADED if any metric is moderately bad
    - DOWN is set externally by anomaly_injector (not computed here)
    - UP otherwise
    """
    # Thresholds for DEGRADED status (lower than CRITICAL alert thresholds)
    if device_type == "ROUTER":
        if latency > 80 or packet_loss > 0.8 or cpu > 75:
            return DeviceStatus.DEGRADED
    elif device_type == "SWITCH":
        if latency > 6 or packet_loss > 0.05 or cpu > 35:
            return DeviceStatus.DEGRADED
    elif device_type == "ACCESS_POINT":
        if latency > 15 or packet_loss > 0.4 or cpu > 30:
            return DeviceStatus.DEGRADED

    return DeviceStatus.UP


def generate_all_metrics(
    devices: list,
    uptime_map: Dict[str, float],
) -> Dict[str, NetworkMetric]:
    """
    Generate metrics for all devices at once.

    Args:
        devices: List of Device objects
        uptime_map: Dict mapping device_id → unix timestamp of "start time"

    Returns:
        Dict mapping device_id → NetworkMetric
    """
    return {
        device.device_id: generate_metric(device, uptime_map[device.device_id])
        for device in devices
    }
