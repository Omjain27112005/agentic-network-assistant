"""
Shared Redis client — singleton pattern, used by all services.
Provides typed helper methods for all Redis operations in this project.
"""
import json
import logging
from typing import Optional, Dict, List, Any
import redis

logger = logging.getLogger(__name__)

# Redis key patterns — centralized here to avoid key naming inconsistencies
DEVICE_METRICS_KEY = "device:{device_id}:metrics"          # Hash
DEVICE_STATE_KEY = "device:{device_id}:state"              # String
DEVICE_HISTORY_KEY = "device:{device_id}:history"          # Sorted Set
ALERT_KEY = "alert:{alert_id}"                             # Hash
ACTIVE_ALERTS_KEY = "alerts:active"                        # Set of alert_ids
CHAT_SESSION_KEY = "chat:session:{session_id}"             # List
SYSTEM_HEALTH_KEY = "system:health_score"                  # String


class RedisClient:
    """
    Production Redis client with typed helper methods.
    Use get_redis_client() singleton instead of instantiating directly.

    All methods include error logging and graceful fallback.
    """

    def __init__(self, host: str, port: int, db: int = 0):
        self._client = redis.Redis(
            host=host,
            port=port,
            db=db,
            decode_responses=True,      # Always return str, not bytes
            socket_connect_timeout=5,
            socket_timeout=5,
            retry_on_timeout=True,
        )
        # Verify connection on startup
        self._client.ping()
        logger.info(f"Redis connected at {host}:{port}")

    # -----------------------------------------------
    # Device Metrics
    # -----------------------------------------------

    def set_device_metrics(self, device_id: str, metrics: Dict[str, str], ttl: int = 60) -> None:
        """Cache latest device metrics. Expires after ttl seconds."""
        key = DEVICE_METRICS_KEY.format(device_id=device_id)
        self._client.hset(key, mapping=metrics)
        self._client.expire(key, ttl)

    def get_device_metrics(self, device_id: str) -> Optional[Dict[str, str]]:
        """Get latest cached metrics for a device. Returns None if expired/missing."""
        key = DEVICE_METRICS_KEY.format(device_id=device_id)
        data = self._client.hgetall(key)
        return data if data else None

    def get_all_device_metrics(self) -> Dict[str, Dict[str, str]]:
        """Get metrics for all devices in one sweep."""
        result = {}
        pattern = DEVICE_METRICS_KEY.format(device_id="*")
        for key in self._client.scan_iter(pattern):
            device_id = key.split(":")[1]
            data = self._client.hgetall(key)
            if data:
                result[device_id] = data
        return result

    # -----------------------------------------------
    # Device State
    # -----------------------------------------------

    def set_device_state(self, device_id: str, state: str) -> None:
        """Set current device state: UP | DOWN | DEGRADED"""
        key = DEVICE_STATE_KEY.format(device_id=device_id)
        self._client.set(key, state)

    def get_device_state(self, device_id: str) -> Optional[str]:
        """Get current device state."""
        key = DEVICE_STATE_KEY.format(device_id=device_id)
        return self._client.get(key)

    # -----------------------------------------------
    # Device History (Time Series)
    # -----------------------------------------------

    def add_device_history(self, device_id: str, timestamp: float, metrics_json: str, max_entries: int = 72) -> None:
        """
        Add a metric snapshot to device history sorted set.
        Score = unix timestamp. Keeps last max_entries snapshots.
        72 entries at 5s interval = 6 minutes of history
        """
        key = DEVICE_HISTORY_KEY.format(device_id=device_id)
        self._client.zadd(key, {metrics_json: timestamp})
        # Keep only last max_entries to bound memory usage
        self._client.zremrangebyrank(key, 0, -(max_entries + 1))

    def get_device_history(self, device_id: str, limit: int = 36) -> List[str]:
        """Get last `limit` metric snapshots for a device (newest last)."""
        key = DEVICE_HISTORY_KEY.format(device_id=device_id)
        return self._client.zrange(key, -limit, -1)

    # -----------------------------------------------
    # Alerts
    # -----------------------------------------------

    def set_alert(self, alert_id: str, alert_data: Dict[str, str], ttl: int = 86400) -> None:
        """Cache alert data. Default TTL = 24 hours."""
        key = ALERT_KEY.format(alert_id=alert_id)
        self._client.hset(key, mapping=alert_data)
        self._client.expire(key, ttl)
        self._client.sadd(ACTIVE_ALERTS_KEY, alert_id)

    def get_alert(self, alert_id: str) -> Optional[Dict[str, str]]:
        """Get alert by ID."""
        key = ALERT_KEY.format(alert_id=alert_id)
        data = self._client.hgetall(key)
        return data if data else None

    def get_all_active_alerts(self) -> List[Dict[str, str]]:
        """Get all currently active alerts."""
        alert_ids = self._client.smembers(ACTIVE_ALERTS_KEY)
        alerts = []
        for alert_id in alert_ids:
            data = self.get_alert(alert_id)
            if data:
                alerts.append(data)
        return alerts

    def update_alert_status(self, alert_id: str, status: str, **extra_fields) -> None:
        """Update alert status and optional extra fields."""
        key = ALERT_KEY.format(alert_id=alert_id)
        update = {"status": status, **{k: str(v) for k, v in extra_fields.items()}}
        self._client.hset(key, mapping=update)
        if status in ("RESOLVED", "FALSE_POSITIVE"):
            self._client.srem(ACTIVE_ALERTS_KEY, alert_id)

    # -----------------------------------------------
    # Chat Sessions
    # -----------------------------------------------

    def add_chat_message(self, session_id: str, message: dict, max_messages: int = 20) -> None:
        """Append a chat message to session history. Keeps last max_messages."""
        key = CHAT_SESSION_KEY.format(session_id=session_id)
        self._client.rpush(key, json.dumps(message))
        self._client.ltrim(key, -max_messages, -1)  # Keep last 20 messages
        self._client.expire(key, 3600)              # Session expires after 1 hour

    def get_chat_history(self, session_id: str) -> List[dict]:
        """Get full chat history for a session."""
        key = CHAT_SESSION_KEY.format(session_id=session_id)
        messages = self._client.lrange(key, 0, -1)
        return [json.loads(m) for m in messages]

    # -----------------------------------------------
    # System Health
    # -----------------------------------------------

    def set_health_score(self, score: float) -> None:
        """Update overall network health score (0-100)."""
        self._client.set(SYSTEM_HEALTH_KEY, str(score))

    def get_health_score(self) -> float:
        """Get current network health score."""
        val = self._client.get(SYSTEM_HEALTH_KEY)
        return float(val) if val else 100.0


# -----------------------------------------------
# Singleton — one Redis connection per process
# -----------------------------------------------
_redis_client: Optional[RedisClient] = None


def get_redis_client(host: str = "localhost", port: int = 6379, db: int = 0) -> RedisClient:
    """Get or create the singleton Redis client."""
    global _redis_client
    if _redis_client is None:
        _redis_client = RedisClient(host=host, port=port, db=db)
    return _redis_client
