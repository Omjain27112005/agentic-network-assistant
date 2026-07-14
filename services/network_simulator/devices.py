"""
Device Registry — defines all 10 network devices and their topology.

Topology (how devices are connected):
        R1 ─────── R2
       / \         / \
      S1  S2     S3  S4
      |   |       |
     AP1 AP2    AP3

R3 connects to R1 and R2 (edge router for external traffic)
"""
from typing import Dict, List
from shared.models.device import Device, DeviceType

# ---------------------------------------------------
# Normal metric ranges per device type
# Used by metrics_generator.py to simulate realistic values
# ---------------------------------------------------
DEVICE_NORMAL_RANGES: Dict[str, Dict] = {
    "ROUTER": {
        "latency_ms":                   (8.0,   25.0),   # min, max
        "packet_loss_percent":          (0.0,   0.3),
        "bandwidth_utilization_percent":(30.0,  70.0),
        "cpu_percent":                  (20.0,  60.0),
        "memory_percent":               (30.0,  65.0),
        "interface_errors_per_min":     (0,     3),
    },
    "SWITCH": {
        "latency_ms":                   (2.0,   10.0),
        "packet_loss_percent":          (0.0,   0.1),
        "bandwidth_utilization_percent":(20.0,  60.0),
        "cpu_percent":                  (10.0,  40.0),
        "memory_percent":               (20.0,  50.0),
        "interface_errors_per_min":     (0,     2),
    },
    "ACCESS_POINT": {
        "latency_ms":                   (5.0,   20.0),
        "packet_loss_percent":          (0.0,   0.5),
        "bandwidth_utilization_percent":(10.0,  55.0),
        "cpu_percent":                  (5.0,   35.0),
        "memory_percent":               (15.0,  45.0),
        "interface_errors_per_min":     (0,     1),
    },
}


# ---------------------------------------------------
# All 10 network devices in the simulated topology
# ---------------------------------------------------
DEVICES: List[Device] = [
    # === Core Routers ===
    Device(
        device_id="R1",
        device_type=DeviceType.ROUTER,
        location="DataCenter-Core",
        ip_address="192.168.1.1",
        neighbors=["R2", "R3", "S1", "S2"],
    ),
    Device(
        device_id="R2",
        device_type=DeviceType.ROUTER,
        location="DataCenter-Core",
        ip_address="192.168.1.2",
        neighbors=["R1", "R3", "S3", "S4"],
    ),
    Device(
        device_id="R3",
        device_type=DeviceType.ROUTER,
        location="DataCenter-Edge",
        ip_address="192.168.1.3",
        neighbors=["R1", "R2"],
    ),

    # === Distribution Switches ===
    Device(
        device_id="S1",
        device_type=DeviceType.SWITCH,
        location="Floor-1-Distribution",
        ip_address="192.168.2.1",
        neighbors=["R1", "AP1"],
    ),
    Device(
        device_id="S2",
        device_type=DeviceType.SWITCH,
        location="Floor-2-Distribution",
        ip_address="192.168.2.2",
        neighbors=["R1", "AP2"],
    ),
    Device(
        device_id="S3",
        device_type=DeviceType.SWITCH,
        location="Floor-3-Distribution",
        ip_address="192.168.2.3",
        neighbors=["R2", "AP3"],
    ),
    Device(
        device_id="S4",
        device_type=DeviceType.SWITCH,
        location="DataCenter-Access",
        ip_address="192.168.2.4",
        neighbors=["R2"],
    ),

    # === Access Points ===
    Device(
        device_id="AP1",
        device_type=DeviceType.ACCESS_POINT,
        location="Floor-1-Zone-A",
        ip_address="192.168.3.1",
        neighbors=["S1"],
    ),
    Device(
        device_id="AP2",
        device_type=DeviceType.ACCESS_POINT,
        location="Floor-2-Zone-A",
        ip_address="192.168.3.2",
        neighbors=["S2"],
    ),
    Device(
        device_id="AP3",
        device_type=DeviceType.ACCESS_POINT,
        location="Floor-3-Zone-A",
        ip_address="192.168.3.3",
        neighbors=["S3"],
    ),
]

# Easy lookup by device_id
DEVICE_MAP: Dict[str, Device] = {d.device_id: d for d in DEVICES}
