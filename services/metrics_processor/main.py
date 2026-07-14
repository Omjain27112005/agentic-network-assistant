"""
Metrics Processor — Service 2

Consumes network metrics from Kafka and stores them in Redis.
This is the bridge between the event stream and the live data cache.

Run: python -m services.metrics_processor.main
"""
import sys
import structlog

from shared.config import get_settings
from shared.kafka.consumer import KafkaConsumerClient
from shared.redis_client import get_redis_client
from services.metrics_processor.consumer import handle_metric_message

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer(),
    ],
)
logger = structlog.get_logger(__name__)


def main() -> None:
    """
    Start the Metrics Processor service.

    Steps:
    1. Verify Redis connection
    2. Start Kafka consumer (blocking loop)
    3. Each message → handle_metric_message()
    """
    settings = get_settings()

    logger.info(
        "metrics_processor.starting",
        kafka_topic=settings.kafka_topic_metrics,
        kafka_group="metrics-processor-group",
        redis_host=settings.redis_host,
    )

    # Verify Redis is reachable before starting Kafka consumer
    try:
        redis = get_redis_client(
            host=settings.redis_host,
            port=settings.redis_port,
            db=settings.redis_db,
        )
        logger.info("redis.connected")
    except Exception as e:
        logger.error("redis.connection_failed", error=str(e))
        sys.exit(1)

    # Start Kafka consumer — this blocks until SIGINT/SIGTERM
    consumer = KafkaConsumerClient(
        bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id="metrics-processor-group",
        topics=[settings.kafka_topic_metrics],
        auto_offset_reset="latest",   # Only process new messages (not backlog)
    )

    logger.info("metrics_processor.ready", status="consuming")

    try:
        consumer.consume(handler=handle_metric_message)
    except Exception as e:
        logger.error("metrics_processor.crashed", error=str(e), exc_info=True)
        sys.exit(1)
    finally:
        logger.info("metrics_processor.stopped")


if __name__ == "__main__":
    main()
