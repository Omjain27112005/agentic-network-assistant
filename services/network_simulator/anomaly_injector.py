"""
Anomaly Injector — randomly injects network failures into metrics.

This is what makes the simulation interesting and tests the AI Agent.
Without anomalies, everything is normal and there's nothing for the AI to diagnose.

Anomaly Types:
1. LATENCY_SPIKE     — Router/Switch gets very high latency (congestion)
2. PACKET_LOSS       — Link degradation, packets being dropped
3. DEVICE_DOWN       — Device completely unreachable
4. CPU_SPIKE         — DDoS or runaway process consuming CPU
5. MEMORY_PRESSURE   — Memory leak, device running out of RAM
6. CASCADING_FAILURE — One device fails → affects neighbors too

Design Philosophy:
- Anomalies are TEMPORARY — they recover after a few cycles (like real incidents)
- Some anomalies cascade to neighboring devices (realistic!)
- Probability is configurable via ANOMALY_INJECTION_RATE env var
"""
import random
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set
from datetime import datetime, timezone

from shared.models.metric import NetworkMetric
from shared.models.device import DeviceStatus
from services.network_simulator.devices import DEVICE_MAP

logger = logging.getLogger(__name__)


@dataclass
class ActiveAnomaly:
    """Tracks an ongoing anomaly and how long it will last."""
    anomaly_type: str
    device_id: str
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    duration_cycles: int = 5      # How many metric cycles this anomaly lasts
    cycles_remaining: int = 5     # Counts down each cycle
    severity: str = "CRITICAL"    # CRITICAL or EMERGENCY


class AnomalyInjector:
    """
    Manages random anomaly injection into network metrics.

    Usage:
        injector = AnomalyInjector(injection_rate=0.05)
        metrics = injector.inject(metrics_dict)  # May modify some metrics
    """

    # Anomaly configs: type → (min_duration, max_duration, is_emergency)
    ANOMALY_CONFIGS = {
        "LATENCY_SPIKE":     (3, 8,  False),  # Lasts 3-8 cycles, CRITICAL
        "PACKET_LOSS":       (4, 10, False),
        "DEVICE_DOWN":       (2, 5,  True),   # EMERGENCY!
        "CPU_SPIKE":         (5, 12, False),
        "MEMORY_PRESSURE":   (6, 15, False),
        "CASCADING_FAILURE": (3, 7,  True),   # EMERGENCY — affects neighbors
    }

    def __init__(self, injection_rate: float = 0.05):
        """
        Args:
            injection_rate: Probability (0-1) that any device gets an anomaly
                           per metric cycle. 0.05 = 5% chance per cycle.
        """
        self.injection_rate = injection_rate
        self._active_anomalies: Dict[str, ActiveAnomaly] = {}  # device_id → anomaly
        self._down_devices: Set[str] = set()

    def inject(self, metrics: Dict[str, NetworkMetric]) -> Dict[str, NetworkMetric]:
        """
        Potentially inject anomalies into the current metric snapshot.

        Steps:
        1. Tick down existing anomalies (may recover)
        2. Maybe start a new anomaly on a random device
        3. Apply all active anomalies to their device metrics

        Args:
            metrics: Current metric snapshot for all devices

        Returns:
            Modified metrics dict (some devices may have injected anomalies)
        """
        # Step 1: Age existing anomalies
        self._tick_anomalies()

        # Step 2: Possibly inject a new anomaly
        self._maybe_inject_new(metrics)

        # Step 3: Apply all active anomalies to metrics
        for device_id, anomaly in self._active_anomalies.items():
            if device_id in metrics:
                metrics[device_id] = self._apply_anomaly(metrics[device_id], anomaly)

        return metrics

    def get_active_anomalies(self) -> List[ActiveAnomaly]:
        """Get list of all currently active anomalies (for logging)."""
        return list(self._active_anomalies.values())

    # -----------------------------------------------
    # Private Methods
    # -----------------------------------------------

    def _tick_anomalies(self) -> None:
        """Count down anomaly duration. Remove recovered ones."""
        recovered = []
        for device_id, anomaly in self._active_anomalies.items():
            anomaly.cycles_remaining -= 1
            if anomaly.cycles_remaining <= 0:
                recovered.append(device_id)
                self._down_devices.discard(device_id)
                logger.info(f"Anomaly RECOVERED: {anomaly.anomaly_type} on {device_id}")

        for device_id in recovered:
            del self._active_anomalies[device_id]

    def _maybe_inject_new(self, metrics: Dict[str, NetworkMetric]) -> None:
        """Roll the dice — maybe inject a new anomaly."""
        # Don't inject if random roll fails
        if random.random() > self.injection_rate:
            return

        # Pick a device that doesn't already have an anomaly
        available = [
            d for d in metrics.keys()
            if d not in self._active_anomalies
        ]
        if not available:
            return

        target_device = random.choice(available)
        anomaly_type = random.choice(list(self.ANOMALY_CONFIGS.keys()))
        min_dur, max_dur, is_emergency = self.ANOMALY_CONFIGS[anomaly_type]
        duration = random.randint(min_dur, max_dur)

        anomaly = ActiveAnomaly(
            anomaly_type=anomaly_type,
            device_id=target_device,
            duration_cycles=duration,
            cycles_remaining=duration,
            severity="EMERGENCY" if is_emergency else "CRITICAL",
        )

        self._active_anomalies[target_device] = anomaly

        if anomaly_type == "DEVICE_DOWN":
            self._down_devices.add(target_device)

        # Cascading: if CASCADING_FAILURE, also affect one random neighbor
        if anomaly_type == "CASCADING_FAILURE":
            device = DEVICE_MAP.get(target_device)
            if device and device.neighbors:
                neighbor = random.choice(device.neighbors)
                if neighbor not in self._active_anomalies:
                    neighbor_anomaly = ActiveAnomaly(
                        anomaly_type="PACKET_LOSS",   # Neighbor gets packet loss
                        device_id=neighbor,
                        duration_cycles=duration - 1,
                        cycles_remaining=duration - 1,
                        severity="CRITICAL",
                    )
                    self._active_anomalies[neighbor] = neighbor_anomaly
                    logger.warning(
                        f"CASCADE: {anomaly_type} on {target_device} "
                        f"→ PACKET_LOSS spreading to neighbor {neighbor}"
                    )

        logger.warning(
            f"Anomaly INJECTED: {anomaly_type} on {target_device} "
            f"(severity={anomaly.severity}, duration={duration} cycles)"
        )

    def _apply_anomaly(
        self,
        metric: NetworkMetric,
        anomaly: ActiveAnomaly,
    ) -> NetworkMetric:
        """
        Modify a metric to reflect the active anomaly.
        Returns a new NetworkMetric with anomalous values.
        """
        data = metric.dict()

        if anomaly.anomaly_type == "LATENCY_SPIKE":
            # Latency jumps to 300-800ms (normal: 8-25ms for routers)
            data["latency_ms"] = round(random.uniform(300, 800), 2)
            data["packet_loss_percent"] = round(random.uniform(2.0, 8.0), 2)
            data["status"] = DeviceStatus.DEGRADED.value

        elif anomaly.anomaly_type == "PACKET_LOSS":
            # Packet loss jumps to 5-30%
            data["packet_loss_percent"] = round(random.uniform(5.0, 30.0), 2)
            data["latency_ms"] = round(data["latency_ms"] * random.uniform(2, 5), 2)
            data["status"] = DeviceStatus.DEGRADED.value

        elif anomaly.anomaly_type == "DEVICE_DOWN":
            # Device completely unreachable
            data["latency_ms"] = 9999.0       # Timeout value
            data["packet_loss_percent"] = 100.0
            data["cpu_percent"] = 0.0
            data["memory_percent"] = 0.0
            data["bandwidth_utilization_percent"] = 0.0
            data["status"] = DeviceStatus.DOWN.value

        elif anomaly.anomaly_type == "CPU_SPIKE":
            # CPU maxes out (DDoS or runaway process)
            data["cpu_percent"] = round(random.uniform(90, 100), 2)
            data["latency_ms"] = round(data["latency_ms"] * random.uniform(3, 8), 2)
            data["status"] = DeviceStatus.DEGRADED.value

        elif anomaly.anomaly_type == "MEMORY_PRESSURE":
            # Memory nearly full (memory leak)
            data["memory_percent"] = round(random.uniform(88, 99), 2)
            data["status"] = DeviceStatus.DEGRADED.value

        elif anomaly.anomaly_type == "CASCADING_FAILURE":
            # Primary device of cascade: severe packet loss + high latency
            data["latency_ms"] = round(random.uniform(500, 1200), 2)
            data["packet_loss_percent"] = round(random.uniform(15.0, 40.0), 2)
            data["status"] = DeviceStatus.DEGRADED.value

        return NetworkMetric(**data)
