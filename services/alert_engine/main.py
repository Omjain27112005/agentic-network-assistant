"""
Alert Engine — Service 3

Consumes network metrics from Kafka, evaluates against thresholds,
and publishes alerts to Kafka 'network.alerts' topic.

This service runs alongside the Metrics Processor.
Both consume from 'network.metrics' but with DIFFERENT consumer group IDs,
so each gets ALL messages independently.

Consumer Groups:
- metrics-processor-group  → Metrics Processor
- alert-engine-group       → Alert Engine (this service)

Run: python -m services.alert_engine.main
"""
import sys
import structlog

from shared.config import get_settings
from shared.kafka.producer import KafkaProducerClient
from shared.kafka.consumer import KafkaConsumerClient
from shared.redis_client import get_redis_client
from services.alert_engine.alert_publisher import AlertPublisher
from services.alert_engine.consumer import AlertEngineConsumer

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
    Start the Alert Engine service.

    Startup sequence:
    1. Verify Redis connection (needed for alert caching)
    2. Create Kafka producer (for publishing alerts)
    3. Create AlertPublisher (wraps producer + Redis)
    4. Create AlertEngineConsumer (wraps publisher + thresholds)
    5. Start Kafka consumer loop (blocking)
    """
    settings = get_settings()

    logger.info(
        "alert_engine.starting",
        input_topic=settings.kafka_topic_metrics,
        output_topic=settings.kafka_topic_alerts,
        consumer_group="alert-engine-group",
    )

    # Step 1: Verify Redis is reachable
    try:
        get_redis_client(
            host=settings.redis_host,
            port=settings.redis_port,
            db=settings.redis_db,
        )
        logger.info("redis.connected")
    except Exception as e:
        logger.error("redis.connection_failed", error=str(e))
        sys.exit(1)

    # Step 2: Create Kafka producer for publishing alerts
    producer = KafkaProducerClient(
        bootstrap_servers=settings.kafka_bootstrap_servers
    )

    # Step 3 & 4: Wire up AlertPublisher and AlertEngineConsumer
    publisher = AlertPublisher(producer=producer)
    engine_consumer = AlertEngineConsumer(publisher=publisher)

    # Step 5: Start Kafka consumer (blocking loop)
    consumer = KafkaConsumerClient(
        bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id="alert-engine-group",         # Different group than metrics-processor!
        topics=[settings.kafka_topic_metrics],  # Same topic as metrics-processor
        auto_offset_reset="latest",
    )

    logger.info("alert_engine.ready", status="consuming")

    try:
        consumer.consume(handler=engine_consumer.handle_metric_message)
    except Exception as e:
        logger.error("alert_engine.crashed", error=str(e), exc_info=True)
        sys.exit(1)
    finally:
        producer.close()
        logger.info("alert_engine.stopped")


if __name__ == "__main__":
    main()
