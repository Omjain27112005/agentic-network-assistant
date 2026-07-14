"""
Alert Publisher — creates Alert objects and publishes them to Kafka.

Two responsibilities:
1. Build a proper Alert from a threshold breach
2. Publish to Kafka 'network.alerts' topic
3. Cache in Redis for fast AI Agent lookups

Cooldown Logic:
- Tracks last alert time per (device_id, alert_type) pair
- If same alert fires again within cooldown window → SKIP
- This prevents alert storms (same alert firing 100x in a minute)

Why cooldown matters:
Without it, a device with high latency would fire 12 alerts/minute
(one per Kafka message). That floods Jira with duplicate tickets.
With cooldown, alert fires ONCE, then suppressed for 60 seconds.
"""
import time
import logging
from typing import Dict, Optional, Tuple

import structlog

from shared.models.alert import Alert, AlertType, Severity
from shared.models.metric import NetworkMetric
from shared.models.device import DeviceStatus
from shared.kafka.producer import KafkaProducerClient
from shared.redis_client import get_redis_client
from shared.config import get_settings

logger = structlog.get_logger(__name__)


class AlertPublisher:
    """
    Creates and publishes alerts with cooldown suppression.

    Usage:
        publisher = AlertPublisher(kafka_producer)
        publisher.maybe_publish(metric, alert_type, severity, description, threshold)
    """

    def __init__(self, producer: KafkaProducerClient):
        self._producer = producer
        self._settings = get_settings()

        # Cooldown tracking: (device_id, alert_type) → unix timestamp of last alert
        self._last_alert_time: Dict[Tuple[str, str], float] = {}

    def maybe_publish_threshold_alert(
        self,
        metric: NetworkMetric,
        alert_type: AlertType,
        severity: Severity,
        threshold_breached: str,
        metric_value: float,
        threshold_value: float,
        cooldown_seconds: int = 60,
    ) -> Optional[Alert]:
        """
        Publish an alert IF cooldown has passed for this device+alert_type combo.

        Args:
            metric: The NetworkMetric that triggered this alert
            alert_type: Type of alert (HIGH_LATENCY, PACKET_LOSS, etc.)
            severity: WARNING or CRITICAL
            threshold_breached: Human readable description e.g. "latency > 300ms (actual: 450ms)"
            metric_value: Actual value that breached threshold
            threshold_value: The threshold that was breached
            cooldown_seconds: Min seconds between same alert on same device

        Returns:
            The Alert object if published, None if suppressed by cooldown
        """
        cooldown_key = (metric.device_id, alert_type.value)
        last_time = self._last_alert_time.get(cooldown_key, 0)
        now = time.time()

        if now - last_time < cooldown_seconds:
            # Still in cooldown window — suppress this alert
            logger.debug(
                "alert.suppressed_by_cooldown",
                device_id=metric.device_id,
                alert_type=alert_type.value,
                cooldown_remaining=round(cooldown_seconds - (now - last_time), 1),
            )
            return None

        # Create the Alert object
        alert = Alert(
            device_id=metric.device_id,
            alert_type=alert_type,
            severity=severity,
            threshold_breached=threshold_breached,
            metric_value=metric_value,
            threshold_value=threshold_value,
        )

        # Publish to Kafka
        self._publish_to_kafka(alert)

        # Cache in Redis for AI Agent quick access
        self._cache_in_redis(alert)

        # Update cooldown tracker
        self._last_alert_time[cooldown_key] = now

        logger.warning(
            "alert.published",
            alert_id=alert.alert_id,
            device_id=alert.device_id,
            alert_type=alert.alert_type,
            severity=alert.severity,
            threshold_breached=alert.threshold_breached,
        )

        return alert

    def publish_device_down_alert(self, metric: NetworkMetric) -> Optional[Alert]:
        """
        Publish an EMERGENCY alert when a device goes completely DOWN.
        Uses a separate longer cooldown (5 min) to avoid repeated emergency tickets.
        """
        cooldown_key = (metric.device_id, AlertType.DEVICE_DOWN.value)
        last_time = self._last_alert_time.get(cooldown_key, 0)
        now = time.time()

        # 5 minute cooldown for DEVICE_DOWN to avoid repeated emergency tickets
        if now - last_time < 300:
            return None

        alert = Alert(
            device_id=metric.device_id,
            alert_type=AlertType.DEVICE_DOWN,
            severity=Severity.EMERGENCY,
            threshold_breached=f"device status = DOWN (latency: {metric.latency_ms}ms, packet_loss: {metric.packet_loss_percent}%)",
            metric_value=metric.packet_loss_percent,
            threshold_value=100.0,
        )

        self._publish_to_kafka(alert)
        self._cache_in_redis(alert)
        self._last_alert_time[cooldown_key] = now

        logger.error(
            "alert.device_down",
            alert_id=alert.alert_id,
            device_id=alert.device_id,
            severity="EMERGENCY",
        )

        return alert

    # -----------------------------------------------
    # Private Helpers
    # -----------------------------------------------

    def _publish_to_kafka(self, alert: Alert) -> None:
        """Publish alert to Kafka 'network.alerts' topic."""
        try:
            self._producer.publish(
                topic=self._settings.kafka_topic_alerts,
                value=alert.to_kafka_payload(),
                key=alert.device_id,  # Partition by device_id
            )
        except Exception as e:
            logger.error(
                "alert.kafka_publish_failed",
                alert_id=alert.alert_id,
                error=str(e),
            )
            raise

    def _cache_in_redis(self, alert: Alert) -> None:
        """Cache alert in Redis so AI Agent can quickly fetch it."""
        try:
            redis = get_redis_client()
            redis.set_alert(
                alert_id=alert.alert_id,
                alert_data=alert.to_redis_hash(),
                ttl=self._settings.redis_ttl_alerts,
            )
        except Exception as e:
            # Redis failure is non-fatal — alert is already in Kafka
            logger.warning(
                "alert.redis_cache_failed",
                alert_id=alert.alert_id,
                error=str(e),
            )
