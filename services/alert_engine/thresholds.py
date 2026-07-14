"""
Alert Thresholds — defines when a metric crosses into WARNING or CRITICAL territory.

Design Decisions:
- Thresholds differ by device type (a router's normal latency != a switch's)
- Two levels: WARNING (monitor) and CRITICAL (AI agent investigates)
- EMERGENCY is set separately when device status == DOWN
- Cooldown prevents alert spam — same alert won't fire again for N seconds

Threshold Table:
┌──────────────────────────┬──────────┬──────────┬──────────┐
│ Metric                   │ ROUTER   │ SWITCH   │ AP       │
├──────────────────────────┼──────────┼──────────┼──────────┤
│ latency_ms (WARNING)     │ > 100ms  │ > 50ms   │ > 80ms   │
│ latency_ms (CRITICAL)    │ > 300ms  │ > 150ms  │ > 200ms  │
│ packet_loss % (WARNING)  │ > 1.0%   │ > 0.5%   │ > 1.5%   │
│ packet_loss % (CRITICAL) │ > 5.0%   │ > 2.0%   │ > 5.0%   │
│ cpu % (WARNING)          │ > 80%    │ > 75%    │ > 70%    │
│ cpu % (CRITICAL)         │ > 95%    │ > 90%    │ > 85%    │
│ memory % (WARNING)       │ > 85%    │ > 80%    │ > 75%    │
│ memory % (CRITICAL)      │ > 95%    │ > 92%    │ > 90%    │
│ interface_errors (WARN)  │ > 10/min │ > 5/min  │ > 3/min  │
│ interface_errors (CRIT)  │ > 50/min │ > 25/min │ > 15/min │
│ bandwidth % (WARNING)    │ > 80%    │ > 75%    │ > 80%    │
│ bandwidth % (CRITICAL)   │ > 95%    │ > 90%    │ > 95%    │
└──────────────────────────┴──────────┴──────────┴──────────┘
"""
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from shared.models.alert import AlertType, Severity


@dataclass
class ThresholdRule:
    """
    A single threshold rule for one metric on one device type.

    Example:
        ThresholdRule(
            metric_field="latency_ms",
            alert_type=AlertType.HIGH_LATENCY,
            warning_value=100.0,
            critical_value=300.0,
            unit="ms",
        )
    """
    metric_field: str          # Attribute name on NetworkMetric
    alert_type: AlertType      # What kind of alert to raise
    warning_value: float       # Threshold for WARNING severity
    critical_value: float      # Threshold for CRITICAL severity
    unit: str = ""             # Human readable unit (ms, %, /min)
    cooldown_seconds: int = 60 # Min seconds between same alert type on same device


# -----------------------------------------------
# Threshold rules per device type
# Each device type has its own list of rules
# -----------------------------------------------
THRESHOLD_RULES: Dict[str, List[ThresholdRule]] = {

    "ROUTER": [
        ThresholdRule(
            metric_field="latency_ms",
            alert_type=AlertType.HIGH_LATENCY,
            warning_value=100.0,
            critical_value=300.0,
            unit="ms",
            cooldown_seconds=60,
        ),
        ThresholdRule(
            metric_field="packet_loss_percent",
            alert_type=AlertType.PACKET_LOSS,
            warning_value=1.0,
            critical_value=5.0,
            unit="%",
            cooldown_seconds=60,
        ),
        ThresholdRule(
            metric_field="cpu_percent",
            alert_type=AlertType.HIGH_CPU,
            warning_value=80.0,
            critical_value=95.0,
            unit="%",
            cooldown_seconds=120,
        ),
        ThresholdRule(
            metric_field="memory_percent",
            alert_type=AlertType.HIGH_MEMORY,
            warning_value=85.0,
            critical_value=95.0,
            unit="%",
            cooldown_seconds=120,
        ),
        ThresholdRule(
            metric_field="interface_errors_per_min",
            alert_type=AlertType.HIGH_INTERFACE_ERRORS,
            warning_value=10.0,
            critical_value=50.0,
            unit="/min",
            cooldown_seconds=60,
        ),
        ThresholdRule(
            metric_field="bandwidth_utilization_percent",
            alert_type=AlertType.BANDWIDTH_SATURATION,
            warning_value=80.0,
            critical_value=95.0,
            unit="%",
            cooldown_seconds=120,
        ),
    ],

    "SWITCH": [
        ThresholdRule(
            metric_field="latency_ms",
            alert_type=AlertType.HIGH_LATENCY,
            warning_value=50.0,
            critical_value=150.0,
            unit="ms",
            cooldown_seconds=60,
        ),
        ThresholdRule(
            metric_field="packet_loss_percent",
            alert_type=AlertType.PACKET_LOSS,
            warning_value=0.5,
            critical_value=2.0,
            unit="%",
            cooldown_seconds=60,
        ),
        ThresholdRule(
            metric_field="cpu_percent",
            alert_type=AlertType.HIGH_CPU,
            warning_value=75.0,
            critical_value=90.0,
            unit="%",
            cooldown_seconds=120,
        ),
        ThresholdRule(
            metric_field="memory_percent",
            alert_type=AlertType.HIGH_MEMORY,
            warning_value=80.0,
            critical_value=92.0,
            unit="%",
            cooldown_seconds=120,
        ),
        ThresholdRule(
            metric_field="interface_errors_per_min",
            alert_type=AlertType.HIGH_INTERFACE_ERRORS,
            warning_value=5.0,
            critical_value=25.0,
            unit="/min",
            cooldown_seconds=60,
        ),
        ThresholdRule(
            metric_field="bandwidth_utilization_percent",
            alert_type=AlertType.BANDWIDTH_SATURATION,
            warning_value=75.0,
            critical_value=90.0,
            unit="%",
            cooldown_seconds=120,
        ),
    ],

    "ACCESS_POINT": [
        ThresholdRule(
            metric_field="latency_ms",
            alert_type=AlertType.HIGH_LATENCY,
            warning_value=80.0,
            critical_value=200.0,
            unit="ms",
            cooldown_seconds=60,
        ),
        ThresholdRule(
            metric_field="packet_loss_percent",
            alert_type=AlertType.PACKET_LOSS,
            warning_value=1.5,
            critical_value=5.0,
            unit="%",
            cooldown_seconds=60,
        ),
        ThresholdRule(
            metric_field="cpu_percent",
            alert_type=AlertType.HIGH_CPU,
            warning_value=70.0,
            critical_value=85.0,
            unit="%",
            cooldown_seconds=120,
        ),
        ThresholdRule(
            metric_field="memory_percent",
            alert_type=AlertType.HIGH_MEMORY,
            warning_value=75.0,
            critical_value=90.0,
            unit="%",
            cooldown_seconds=120,
        ),
        ThresholdRule(
            metric_field="interface_errors_per_min",
            alert_type=AlertType.HIGH_INTERFACE_ERRORS,
            warning_value=3.0,
            critical_value=15.0,
            unit="/min",
            cooldown_seconds=60,
        ),
        ThresholdRule(
            metric_field="bandwidth_utilization_percent",
            alert_type=AlertType.BANDWIDTH_SATURATION,
            warning_value=80.0,
            critical_value=95.0,
            unit="%",
            cooldown_seconds=120,
        ),
    ],
}


def evaluate_metric_against_rules(
    metric_value: float,
    rule: ThresholdRule,
) -> Optional[Tuple[Severity, str]]:
    """
    Check if a metric value breaches any threshold for a given rule.

    Returns:
        Tuple of (Severity, human_readable_description) if breached
        None if within normal range

    Priority: CRITICAL checked first (higher priority than WARNING)
    """
    if metric_value >= rule.critical_value:
        description = (
            f"{rule.metric_field} > {rule.critical_value}{rule.unit} "
            f"(actual: {metric_value}{rule.unit})"
        )
        return Severity.CRITICAL, description

    if metric_value >= rule.warning_value:
        description = (
            f"{rule.metric_field} > {rule.warning_value}{rule.unit} "
            f"(actual: {metric_value}{rule.unit})"
        )
        return Severity.WARNING, description

    return None  # Within normal range — no alert
