"""
Alert Engine Consumer — evaluates every incoming metric against thresholds.

This is the brain of the Alert Engine.
For each metric message from Kafka:
1. Check device status — if DOWN → fire EMERGENCY alert
2. Get threshold rules for this device type
3. Evaluate each metric field against its rule
4. Fire alert if threshold breached (respecting cooldown)

Why evaluate ALL rules per message?
A device could simultaneously have high latency AND high CPU.
Each is a separate alert with a separate investigation path.
"""
import structlog
from typing import Dict

from shared.models.metric import NetworkMetric
from shared.models.device import DeviceStatus
from services.alert_engine.thresholds import THRESHOLD_RULES, evaluate_metric_against_rules
from services.alert_engine.alert_publisher import AlertPublisher

logger = structlog.get_logger(__name__)

# Cache device types — fetched once from Redis or hardcoded from devices registry
# This avoids a Redis lookup on every single metric message
DEVICE_TYPE_MAP: Dict[str, str] = {
    "R1": "ROUTER", "R2": "ROUTER", "R3": "ROUTER",
    "S1": "SWITCH", "S2": "SWITCH", "S3": "SWITCH", "S4": "SWITCH",
    "AP1": "ACCESS_POINT", "AP2": "ACCESS_POINT", "AP3": "ACCESS_POINT",
}


class AlertEngineConsumer:
    """
    Stateful consumer that evaluates metrics against thresholds.
    Stateful because AlertPublisher tracks cooldowns internally.
    """

    def __init__(self, publisher: AlertPublisher):
        self._publisher = publisher
        self._alerts_fired = 0  # Metrics for logging

    def handle_metric_message(self, topic: str, value: str) -> None:
        """
        Handler called by KafkaConsumerClient for each metric message.

        Steps:
        1. Deserialize JSON → NetworkMetric
        2. Check if device is DOWN → EMERGENCY alert
        3. Evaluate all threshold rules for this device type
        4. Fire alerts for any breaches (with cooldown)
        """
        try:
            metric = NetworkMetric.from_kafka_payload(value)
        except Exception as e:
            logger.error("metric.deserialize_failed", error=str(e))
            return

        # Step 1: Check if device is completely DOWN → EMERGENCY
        status = metric.status if isinstance(metric.status, str) else metric.status.value
        if status == DeviceStatus.DOWN.value:
            alert = self._publisher.publish_device_down_alert(metric)
            if alert:
                self._alerts_fired += 1
                logger.error(
                    "emergency.device_down",
                    device_id=metric.device_id,
                    alert_id=alert.alert_id,
                )
            return  # If device is DOWN, skip threshold checks (values are meaningless)

        # Step 2: Get threshold rules for this device type
        device_type = DEVICE_TYPE_MAP.get(metric.device_id)
        if not device_type:
            logger.warning("device.unknown_type", device_id=metric.device_id)
            return

        rules = THRESHOLD_RULES.get(device_type, [])

        # Step 3: Evaluate each rule against current metric values
        for rule in rules:
            # Get the actual metric value for this rule's field
            metric_value = getattr(metric, rule.metric_field, None)
            if metric_value is None:
                continue

            # Check against thresholds
            result = evaluate_metric_against_rules(metric_value, rule)
            if result is None:
                continue  # Within normal range

            severity, threshold_breached = result

            # Step 4: Fire alert (respects cooldown)
            alert = self._publisher.maybe_publish_threshold_alert(
                metric=metric,
                alert_type=rule.alert_type,
                severity=severity,
                threshold_breached=threshold_breached,
                metric_value=float(metric_value),
                threshold_value=(
                    rule.critical_value
                    if severity.value == "CRITICAL"
                    else rule.warning_value
                ),
                cooldown_seconds=rule.cooldown_seconds,
            )

            if alert:
                self._alerts_fired += 1
                logger.warning(
                    "alert.fired",
                    device_id=metric.device_id,
                    alert_type=rule.alert_type.value,
                    severity=severity.value,
                    value=metric_value,
                    total_alerts_fired=self._alerts_fired,
                )
