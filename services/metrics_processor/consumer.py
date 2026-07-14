"""
Metrics Processor Consumer — reads from Kafka, writes to Redis.

This is the handler function passed to KafkaConsumerClient.
Each call processes ONE message from the 'network.metrics' topic.
"""
import logging
import structlog
from shared.models.metric import NetworkMetric
from services.metrics_processor.redis_writer import (
    write_metric_to_redis,
    update_network_health_score,
)

logger = structlog.get_logger(__name__)

# Update health score every N messages (not every single message — saves Redis writes)
HEALTH_SCORE_UPDATE_INTERVAL = 10
_message_count = 0


def handle_metric_message(topic: str, value: str) -> None:
    """
    Handler called by KafkaConsumerClient for each incoming metric message.

    Flow:
        Kafka message → deserialize → write to Redis → (periodically) update health score

    Args:
        topic: Kafka topic name (should always be 'network.metrics')
        value: JSON string metric payload
    """
    global _message_count
    _message_count += 1

    try:
        # Deserialize JSON string → NetworkMetric Pydantic model
        metric = NetworkMetric.from_kafka_payload(value)

        # Write to Redis (3 writes: latest, state, history)
        write_metric_to_redis(metric)

        # Update health score every 10 messages (one full cycle of all 10 devices)
        if _message_count % HEALTH_SCORE_UPDATE_INTERVAL == 0:
            health_score = update_network_health_score()
            logger.info(
                "health_score.updated",
                score=health_score,
                messages_processed=_message_count,
            )

        logger.debug(
            "metric.processed",
            device_id=metric.device_id,
            status=metric.status,
            latency_ms=metric.latency_ms,
            cpu_percent=metric.cpu_percent,
        )

    except ValueError as e:
        # Bad JSON or validation error — log and skip (don't crash)
        logger.error("metric.deserialize_failed", error=str(e), raw_value=value[:200])
    except Exception as e:
        logger.error("metric.processing_failed", error=str(e), exc_info=True)
        # Re-raise to let consumer handle it (it won't crash, just logs)
        raise
