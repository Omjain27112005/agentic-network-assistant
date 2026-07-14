"""
Network Simulator — Service 1

Entry point. Orchestrates the entire simulation loop:
1. Every INTERVAL seconds, generate metrics for all 10 devices
2. Optionally inject anomalies
3. Publish each device's metric to Kafka 'network.metrics' topic

Run: python -m services.network_simulator.main
"""
import sys
import time
import logging
import structlog
from datetime import datetime, timezone

from shared.config import get_settings
from shared.kafka.producer import KafkaProducerClient
from services.network_simulator.devices import DEVICES
from services.network_simulator.metrics_generator import generate_all_metrics
from services.network_simulator.anomaly_injector import AnomalyInjector

# -----------------------------------------------
# Structured JSON Logging (production standard)
# -----------------------------------------------
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
    Main simulation loop.

    Flow:
        startup → initialize devices → loop:
            generate metrics → inject anomalies → publish to Kafka → sleep
    """
    settings = get_settings()

    logger.info(
        "network_simulator.starting",
        device_count=len(DEVICES),
        interval_seconds=settings.simulator_interval_seconds,
        anomaly_rate=settings.anomaly_injection_rate,
        kafka_topic=settings.kafka_topic_metrics,
    )

    # Initialize Kafka producer
    producer = KafkaProducerClient(
        bootstrap_servers=settings.kafka_bootstrap_servers
    )

    # Initialize anomaly injector
    injector = AnomalyInjector(
        injection_rate=settings.anomaly_injection_rate
    )

    # Track when each device "started" for uptime calculation
    # All devices start simultaneously when the simulator starts
    start_time = time.time()
    uptime_map = {device.device_id: start_time for device in DEVICES}

    cycle = 0  # Track how many cycles we've run (useful for debugging)

    logger.info("network_simulator.ready", status="running")

    try:
        while True:
            cycle += 1
            cycle_start = time.time()

            # Step 1: Generate normal metrics for all devices
            metrics = generate_all_metrics(DEVICES, uptime_map)

            # Step 2: Maybe inject anomalies into some devices
            metrics = injector.inject(metrics)

            # Log if there are active anomalies this cycle
            active_anomalies = injector.get_active_anomalies()
            if active_anomalies:
                for anomaly in active_anomalies:
                    logger.warning(
                        "anomaly.active",
                        type=anomaly.anomaly_type,
                        device=anomaly.device_id,
                        severity=anomaly.severity,
                        cycles_remaining=anomaly.cycles_remaining,
                    )

            # Step 3: Publish each device's metric to Kafka
            published_count = 0
            for device_id, metric in metrics.items():
                try:
                    producer.publish(
                        topic=settings.kafka_topic_metrics,
                        value=metric.to_kafka_payload(),
                        key=device_id,   # Partition by device_id — ordered per device
                    )
                    published_count += 1
                except Exception as e:
                    logger.error(
                        "kafka.publish_failed",
                        device_id=device_id,
                        error=str(e),
                    )

            # Flush to ensure all messages are sent before sleeping
            producer.flush(timeout=2.0)

            # Log cycle summary
            cycle_duration_ms = round((time.time() - cycle_start) * 1000, 2)
            logger.info(
                "cycle.complete",
                cycle=cycle,
                published=published_count,
                total_devices=len(DEVICES),
                active_anomalies=len(active_anomalies),
                duration_ms=cycle_duration_ms,
            )

            # Sleep until next cycle
            # Subtract time spent in this cycle for accurate interval
            sleep_time = max(
                0,
                settings.simulator_interval_seconds - (time.time() - cycle_start)
            )
            time.sleep(sleep_time)

    except KeyboardInterrupt:
        logger.info("network_simulator.stopping", reason="KeyboardInterrupt")
    except Exception as e:
        logger.error("network_simulator.crashed", error=str(e), exc_info=True)
        sys.exit(1)
    finally:
        producer.close()
        logger.info("network_simulator.stopped")


if __name__ == "__main__":
    main()
