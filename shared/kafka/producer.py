"""
Shared Kafka Producer — used by all services that publish events.
Wraps confluent-kafka with retry logic and structured logging.
"""
import json
import logging
from typing import Optional
from confluent_kafka import Producer, KafkaException

logger = logging.getLogger(__name__)


class KafkaProducerClient:
    """
    Thread-safe Kafka producer wrapper.
    
    Usage:
        producer = KafkaProducerClient(bootstrap_servers="localhost:9092")
        producer.publish("network.metrics", key="R1", value=metric.to_kafka_payload())
    """

    def __init__(self, bootstrap_servers: str):
        self._config = {
            "bootstrap.servers": bootstrap_servers,
            "acks": "all",                  # Wait for all replicas to acknowledge
            "retries": 3,                   # Retry failed sends 3 times
            "retry.backoff.ms": 300,        # Wait 300ms between retries
            "enable.idempotence": True,     # Exactly-once delivery guarantee
            "compression.type": "snappy",   # Compress messages for efficiency
        }
        self._producer: Optional[Producer] = None

    def _get_producer(self) -> Producer:
        """Lazy initialization — create producer only when first needed."""
        if self._producer is None:
            self._producer = Producer(self._config)
            logger.info("Kafka producer connected")
        return self._producer

    def publish(
        self,
        topic: str,
        value: str,
        key: Optional[str] = None,
    ) -> None:
        """
        Publish a message to a Kafka topic.
        
        Args:
            topic: Kafka topic name e.g. "network.metrics"
            value: Message payload as JSON string
            key: Optional partition key — use device_id for ordered per-device messages
        """
        try:
            producer = self._get_producer()
            producer.produce(
                topic=topic,
                value=value.encode("utf-8"),
                key=key.encode("utf-8") if key else None,
                on_delivery=self._delivery_callback,
            )
            producer.poll(0)  # Trigger delivery callbacks without blocking

            logger.debug(f"Published to {topic} | key={key} | size={len(value)} bytes")

        except KafkaException as e:
            logger.error(f"Failed to publish to {topic}: {e}")
            raise
        except BufferError:
            # Producer queue full — flush and retry
            logger.warning("Producer queue full, flushing...")
            producer.flush(timeout=5)
            self.publish(topic, value, key)

    def flush(self, timeout: float = 10.0) -> None:
        """Wait for all in-flight messages to be delivered."""
        if self._producer:
            self._producer.flush(timeout=timeout)

    def close(self) -> None:
        """Graceful shutdown — flush all pending messages."""
        self.flush()
        logger.info("Kafka producer closed")

    @staticmethod
    def _delivery_callback(err, msg) -> None:
        """Called by Kafka when message delivery is confirmed or fails."""
        if err:
            logger.error(f"Message delivery failed: {err}")
        else:
            logger.debug(
                f"Message delivered | topic={msg.topic()} | "
                f"partition={msg.partition()} | offset={msg.offset()}"
            )
