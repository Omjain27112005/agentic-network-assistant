"""
Redis Writer — writes consumed metrics into Redis.

Responsibilities:
1. Cache latest metric snapshot for each device (Hash, TTL=60s)
2. Update device state string (UP/DOWN/DEGRADED)
3. Append to device history time-series (Sorted Set, capped at 72 entries)
4. Recalculate and update overall network health score
"""
import json
import time
import logging
from typing import Dict

from shared.models.metric import NetworkMetric
from shared.models.device import DeviceStatus
from shared.redis_client import get_redis_client

logger = logging.getLogger(__name__)

# All device IDs we know about — used for health score calculation
ALL_DEVICE_IDS = ["R1", "R2", "R3", "S1", "S2", "S3", "S4", "AP1", "AP2", "AP3"]


def write_metric_to_redis(metric: NetworkMetric) -> None:
    """
    Persist a single device metric snapshot to Redis.

    Three writes happen per metric:
    1. HSET  device:{id}:metrics  — latest snapshot (expires in 60s)
    2. SET   device:{id}:state    — current UP/DOWN/DEGRADED string
    3. ZADD  device:{id}:history  — time-series entry (score = unix timestamp)

    Args:
        metric: The NetworkMetric to persist
    """
    redis = get_redis_client()

    try:
        # 1. Cache latest metrics (TTL = 60s, auto-expires if device goes silent)
        redis.set_device_metrics(
            device_id=metric.device_id,
            metrics=metric.to_redis_hash(),
            ttl=60,
        )

        # 2. Update device state for fast status lookups
        redis.set_device_state(
            device_id=metric.device_id,
            state=metric.status if isinstance(metric.status, str) else metric.status.value,
        )

        # 3. Add to history time-series
        # Score = unix timestamp for time-ordered retrieval
        timestamp = metric.timestamp.timestamp()
        history_snapshot = json.dumps({
            "timestamp": metric.timestamp.isoformat(),
            "latency_ms": metric.latency_ms,
            "packet_loss_percent": metric.packet_loss_percent,
            "cpu_percent": metric.cpu_percent,
            "memory_percent": metric.memory_percent,
            "bandwidth_utilization_percent": metric.bandwidth_utilization_percent,
            "status": metric.status if isinstance(metric.status, str) else metric.status.value,
        })
        redis.add_device_history(
            device_id=metric.device_id,
            timestamp=timestamp,
            metrics_json=history_snapshot,
        )

        logger.debug(
            f"Written to Redis | device={metric.device_id} | "
            f"status={metric.status} | latency={metric.latency_ms}ms"
        )

    except Exception as e:
        logger.error(f"Redis write failed for {metric.device_id}: {e}")
        raise


def update_network_health_score() -> float:
    """
    Recalculate and store the overall network health score (0-100).

    Formula:
        - Start at 100
        - Each DEGRADED device: -5 points
        - Each DOWN device: -15 points
        - Each missing device (no data): -10 points

    Returns:
        The calculated health score
    """
    redis = get_redis_client()
    score = 100.0

    for device_id in ALL_DEVICE_IDS:
        state = redis.get_device_state(device_id)

        if state is None:
            # Device has no data — possibly just started up
            score -= 10
        elif state == DeviceStatus.DEGRADED.value:
            score -= 5
        elif state == DeviceStatus.DOWN.value:
            score -= 15

    score = max(0.0, score)  # Never below 0
    redis.set_health_score(score)

    logger.debug(f"Network health score updated: {score}/100")
    return score
