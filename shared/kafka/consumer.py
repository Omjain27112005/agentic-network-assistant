"""
Shared Kafka Consumer — base class for all consumer services.
Provides auto-commit, graceful shutdown, and error handling.
"""
import logging
import signal
from typing import Callable, List
from confluent_kafka import Consumer, KafkaError, KafkaException, Message

logger = logging.getLogger(__name__)


class KafkaConsumerClient:
    """
    Base Kafka consumer with graceful shutdown support.
    
    Usage:
        consumer = KafkaConsumerClient(
            bootstrap_servers="localhost:9092",
            group_id="metrics-processor-group",
            topics=["network.metrics"],
        )
        consumer.consume(handler=process_message)
    """

    def __init__(
        self,
        bootstrap_servers: str,
        group_id: str,
        topics: List[str],
        auto_offset_reset: str = "latest",
    ):
        self._config = {
            "bootstrap.servers": bootstrap_servers,
            "group.id": group_id,
            "auto.offset.reset": auto_offset_reset,  # "latest" = only new msgs, "earliest" = from beginning
            "enable.auto.commit": True,
            "auto.commit.interval.ms": 5000,          # Commit offsets every 5 seconds
            "session.timeout.ms": 30000,
            "max.poll.interval.ms": 300000,
        }
        self._topics = topics
        self._consumer: Consumer = Consumer(self._config)
        self._running = False

        # Register signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._shutdown_handler)
        signal.signal(signal.SIGTERM, self._shutdown_handler)

    def consume(self, handler: Callable[[str, str], None]) -> None:
        """
        Start consuming messages and call handler for each one.
        Runs in a blocking loop until SIGINT/SIGTERM received.
        
        Args:
            handler: Callback function(topic, message_value) to process each message
        """
        self._consumer.subscribe(self._topics)
        self._running = True

        logger.info(f"Consumer started | topics={self._topics} | group={self._config['group.id']}")

        try:
            while self._running:
                msg: Message = self._consumer.poll(timeout=1.0)

                if msg is None:
                    continue  # No message within timeout — loop again

                if msg.error():
                    if msg.error().code() == KafkaError._PARTITION_EOF:
                        # Normal — reached end of partition, not an error
                        logger.debug(f"Reached end of partition: {msg.topic()}/{msg.partition()}")
                    else:
                        logger.error(f"Consumer error: {msg.error()}")
                    continue

                try:
                    topic = msg.topic()
                    value = msg.value().decode("utf-8")
                    key = msg.key().decode("utf-8") if msg.key() else None

                    logger.debug(f"Received message | topic={topic} | key={key}")

                    handler(topic, value)

                except Exception as e:
                    # Log processing error but DO NOT crash — keep consuming
                    logger.error(f"Error processing message from {msg.topic()}: {e}", exc_info=True)

        except KafkaException as e:
            logger.error(f"Fatal Kafka error: {e}")
            raise
        finally:
            self._consumer.close()
            logger.info("Consumer closed")

    def _shutdown_handler(self, signum, frame) -> None:
        """Handle SIGINT/SIGTERM — stop consuming gracefully."""
        logger.info(f"Shutdown signal received ({signum}) — stopping consumer...")
        self._running = False
