"""
Action Executor — Service 5

Consumes AI Agent results from Kafka 'network.actions' topic.
For each result: creates Jira ticket + saves incident to PostgreSQL.

This service is the final step in the autonomous incident response pipeline:
  Alert Engine → AI Agent → Action Executor → Jira + PostgreSQL

Run: python -m services.action_executor.main
"""
import json
import sys
import structlog

from shared.config import get_settings
from shared.kafka.consumer import KafkaConsumerClient
from shared.redis_client import get_redis_client
from services.action_executor.jira_client import JiraClient
from services.action_executor.db import Database
from services.action_executor.action_handler import ActionHandler

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer(),
    ],
)
logger = structlog.get_logger(__name__)


def build_action_message_handler(handler: ActionHandler):
    """
    Factory: builds the Kafka handler closure with ActionHandler injected.
    """
    def handle_action_message(topic: str, value: str) -> None:
        """
        Process one message from network.actions topic.
        Each message = one completed AI Agent investigation.
        """
        try:
            payload = json.loads(value)
        except json.JSONDecodeError as e:
            logger.error("action.deserialize_failed", error=str(e), raw=value[:200])
            return

        alert_id = payload.get("alert_id", "UNKNOWN")
        device_id = payload.get("device_id", "UNKNOWN")

        logger.info(
            "action.received",
            alert_id=alert_id,
            device_id=device_id,
            confidence=payload.get("confidence_score"),
            success=payload.get("success"),
        )

        # Reconstruct minimal alert_data from the agent_result payload
        # The full alert_data is embedded in the payload for this purpose
        alert_data = {
            "alert_id": alert_id,
            "device_id": device_id,
            "alert_type": payload.get("alert_type", "UNKNOWN"),
            "severity": payload.get("severity_assessment", "CRITICAL"),
            "threshold_breached": payload.get("root_cause", ""),
        }

        try:
            handler.handle(agent_result=payload, alert_data=alert_data)
        except Exception as e:
            logger.error(
                "action.handler_failed",
                alert_id=alert_id,
                error=str(e),
                exc_info=True,
            )

    return handle_action_message


def main() -> None:
    """
    Start the Action Executor service.

    Startup sequence:
    1. Connect to PostgreSQL (with retry)
    2. Connect to Redis
    3. Initialize Jira client
    4. Start Kafka consumer loop
    """
    settings = get_settings()

    logger.info(
        "action_executor.starting",
        input_topic=settings.kafka_topic_actions,
        consumer_group="action-executor-group",
        jira_configured=bool(settings.jira_base_url),
    )

    # Step 1: Connect to PostgreSQL
    try:
        db = Database(database_url=settings.database_url)
        logger.info("postgres.connected")
    except Exception as e:
        logger.error("postgres.connection_failed", error=str(e))
        sys.exit(1)

    # Step 2: Connect to Redis
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

    # Step 3: Initialize Jira client
    jira = JiraClient(
        base_url=settings.jira_base_url,
        email=settings.jira_email,
        api_token=settings.jira_api_token,
        project_key=settings.jira_project_key,
    )

    # Step 4: Build action handler
    action_handler = ActionHandler(jira=jira, db=db)
    message_handler = build_action_message_handler(action_handler)

    # Step 5: Start Kafka consumer
    consumer = KafkaConsumerClient(
        bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id="action-executor-group",
        topics=[settings.kafka_topic_actions],
        auto_offset_reset="latest",
    )

    logger.info("action_executor.ready", status="consuming")

    try:
        consumer.consume(handler=message_handler)
    except Exception as e:
        logger.error("action_executor.crashed", error=str(e), exc_info=True)
        sys.exit(1)
    finally:
        jira.close()
        db.dispose()
        logger.info("action_executor.stopped")


if __name__ == "__main__":
    main()
