"""
AI Agent Service — Service 4

Consumes network alerts from Kafka, runs ReAct investigation,
and publishes structured action results to Kafka 'network.actions' topic.

Key Design Decisions:
1. Only investigate CRITICAL and EMERGENCY alerts (not WARNING — too noisy)
2. Update alert status in Redis during investigation (OPEN → INVESTIGATING)
3. Update alert status after investigation (INVESTIGATING → RESOLVED or stays OPEN)
4. Publish AgentResult to network.actions for Action Executor to handle
5. Single-threaded consumer — investigation is sequential (one at a time)
   Future improvement: async concurrent investigation with semaphore

Run: python -m services.ai_agent.main
"""
import json
import sys
import structlog

from shared.config import get_settings
from shared.kafka.producer import KafkaProducerClient
from shared.kafka.consumer import KafkaConsumerClient
from shared.redis_client import get_redis_client
from shared.models.alert import Alert, AlertStatus, Severity
from services.ai_agent.groq_client import GroqLLMClient
from services.ai_agent.agent import NetworkInvestigationAgent

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer(),
    ],
)
logger = structlog.get_logger(__name__)

# Only investigate these severity levels (WARNING is too noisy for AI)
INVESTIGATE_SEVERITIES = {
    Severity.CRITICAL.value,
    Severity.EMERGENCY.value,
}


def build_alert_handler(agent: NetworkInvestigationAgent, producer: KafkaProducerClient, settings):
    """
    Factory that builds the Kafka message handler with all dependencies injected.

    Why a factory pattern?
    The handler function needs access to agent, producer, and settings,
    but KafkaConsumerClient.consume() only accepts handler(topic, value).
    Factory creates a closure that captures these dependencies cleanly.
    """

    def handle_alert_message(topic: str, value: str) -> None:
        """
        Handler called for each message on network.alerts topic.
        
        Steps:
        1. Deserialize alert JSON
        2. Skip if severity is not CRITICAL/EMERGENCY
        3. Mark alert as INVESTIGATING in Redis
        4. Run AI agent investigation (ReAct loop)
        5. Update alert status in Redis
        6. Publish AgentResult to network.actions
        """
        redis = get_redis_client()

        # Step 1: Deserialize
        try:
            alert_data = json.loads(value)
        except json.JSONDecodeError as e:
            logger.error("alert.deserialize_failed", error=str(e), raw_value=value[:200])
            return

        alert_id = alert_data.get("alert_id", "unknown")
        device_id = alert_data.get("device_id", "unknown")
        severity = alert_data.get("severity", "INFO")
        alert_type = alert_data.get("alert_type", "UNKNOWN")

        logger.info(
            "alert.received",
            alert_id=alert_id,
            device_id=device_id,
            severity=severity,
            alert_type=alert_type,
        )

        # Step 2: Skip non-critical alerts
        if severity not in INVESTIGATE_SEVERITIES:
            logger.info(
                "alert.skipped",
                alert_id=alert_id,
                severity=severity,
                reason=f"Only investigating CRITICAL and EMERGENCY. Got: {severity}",
            )
            return

        # Step 3: Mark alert as INVESTIGATING in Redis
        try:
            redis.update_alert_status(alert_id, AlertStatus.INVESTIGATING.value)
            logger.info("alert.status_updated", alert_id=alert_id, status="INVESTIGATING")
        except Exception as e:
            logger.warning("alert.redis_status_update_failed", alert_id=alert_id, error=str(e))
            # Non-fatal — continue investigation regardless

        # Step 4: Run ReAct investigation
        logger.info(
            "agent.starting_investigation",
            alert_id=alert_id,
            device_id=device_id,
            severity=severity,
        )

        result = agent.investigate(alert_data)

        # Step 5: Update Redis alert status based on result
        try:
            if result.success and result.confidence_score >= 0.6:
                redis.update_alert_status(
                    alert_id,
                    AlertStatus.RESOLVED.value,
                    root_cause=result.root_cause[:200],  # Redis values are strings
                    confidence=str(result.confidence_score),
                )
            else:
                # Low confidence — keep it open for manual review
                redis.update_alert_status(
                    alert_id,
                    AlertStatus.OPEN.value,
                    root_cause=result.root_cause[:200],
                )
        except Exception as e:
            logger.warning("alert.redis_update_failed", alert_id=alert_id, error=str(e))

        # Step 6: Publish AgentResult to network.actions for Action Executor
        try:
            producer.publish(
                topic=settings.kafka_topic_actions,
                value=result.to_kafka_payload(),
                key=device_id,
            )
            producer.flush(timeout=5.0)

            logger.info(
                "agent.result_published",
                alert_id=alert_id,
                device_id=device_id,
                root_cause=result.root_cause[:100],
                confidence=result.confidence_score,
                success=result.success,
                iterations=result.iterations_used,
                tool_calls=result.tool_calls_made,
                duration_seconds=result.duration_seconds,
            )

        except Exception as e:
            logger.error(
                "agent.result_publish_failed",
                alert_id=alert_id,
                error=str(e),
            )

    return handle_alert_message


def main() -> None:
    """
    Start the AI Agent service.

    Startup sequence:
    1. Validate GROQ_API_KEY is present
    2. Verify Redis connection
    3. Initialize Groq LLM client
    4. Initialize Agent
    5. Start Kafka consumer loop (blocking)
    """
    settings = get_settings()

    logger.info(
        "ai_agent.starting",
        input_topic=settings.kafka_topic_alerts,
        output_topic=settings.kafka_topic_actions,
        consumer_group="ai-agent-group",
        llm_model=settings.groq_model,
    )

    # Step 1: Validate Groq API key
    if not settings.groq_api_key:
        logger.error(
            "ai_agent.startup_failed",
            reason="GROQ_API_KEY is not set in .env. Get a free key at console.groq.com",
        )
        sys.exit(1)

    # Step 2: Verify Redis connection
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

    # Step 3: Initialize Groq client
    try:
        groq_client = GroqLLMClient(
            api_key=settings.groq_api_key,
            model=settings.groq_model,
        )
        logger.info("groq_client.initialized", model=settings.groq_model)
    except Exception as e:
        logger.error("groq_client.init_failed", error=str(e))
        sys.exit(1)

    # Step 4: Initialize agent
    agent = NetworkInvestigationAgent(groq_client=groq_client)

    # Step 5: Build Kafka producer (for publishing action results)
    producer = KafkaProducerClient(
        bootstrap_servers=settings.kafka_bootstrap_servers
    )

    # Build handler with dependencies injected via closure
    alert_handler = build_alert_handler(agent, producer, settings)

    # Start Kafka consumer
    consumer = KafkaConsumerClient(
        bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id="ai-agent-group",           # Unique consumer group
        topics=[settings.kafka_topic_alerts],  # Reads from network.alerts
        auto_offset_reset="latest",
    )

    logger.info(
        "ai_agent.ready",
        status="consuming",
        investigates_severities=list(INVESTIGATE_SEVERITIES),
    )

    try:
        consumer.consume(handler=alert_handler)
    except Exception as e:
        logger.error("ai_agent.crashed", error=str(e), exc_info=True)
        sys.exit(1)
    finally:
        producer.close()
        logger.info("ai_agent.stopped")


if __name__ == "__main__":
    main()
