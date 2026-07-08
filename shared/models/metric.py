"""
Shared Pydantic models for Network Metrics.
Used by: Network Simulator, Metrics Processor, Alert Engine, API Gateway
"""
import json
from datetime import datetime
from pydantic import BaseModel, Field
from shared.models.device import DeviceStatus


class NetworkMetric(BaseModel):
    """
    A single metric snapshot from one network device.
    Published to Kafka 'network.metrics' topic every 5 seconds.
    Cached in Redis with TTL for fast API reads.
    """
    device_id: str = Field(..., description="Device this metric belongs to")
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    # Core network health metrics
    latency_ms: float = Field(..., ge=0, description="Round-trip latency in milliseconds")
    packet_loss_percent: float = Field(..., ge=0, le=100, description="% of packets dropped")
    bandwidth_utilization_percent: float = Field(..., ge=0, le=100, description="% of max bandwidth used")

    # Device resource metrics
    cpu_percent: float = Field(..., ge=0, le=100, description="CPU usage percentage")
    memory_percent: float = Field(..., ge=0, le=100, description="Memory usage percentage")
    interface_errors_per_min: int = Field(..., ge=0, description="Network interface errors per minute")
    uptime_seconds: int = Field(..., ge=0, description="Seconds since last reboot")

    # Computed status
    status: DeviceStatus = Field(default=DeviceStatus.UP)

    class Config:
        use_enum_values = True

    def to_kafka_payload(self) -> str:
        """Serialize to JSON string for Kafka message value."""
        data = self.dict()
        data["timestamp"] = self.timestamp.isoformat()
        return json.dumps(data)

    @classmethod
    def from_kafka_payload(cls, payload: str) -> "NetworkMetric":
        """Deserialize from Kafka message value."""
        data = json.loads(payload)
        return cls(**data)

    def to_redis_hash(self) -> dict:
        """Serialize for Redis HSET — all values must be strings."""
        return {
            "device_id": self.device_id,
            "timestamp": self.timestamp.isoformat(),
            "latency_ms": str(self.latency_ms),
            "packet_loss_percent": str(self.packet_loss_percent),
            "bandwidth_utilization_percent": str(self.bandwidth_utilization_percent),
            "cpu_percent": str(self.cpu_percent),
            "memory_percent": str(self.memory_percent),
            "interface_errors_per_min": str(self.interface_errors_per_min),
            "uptime_seconds": str(self.uptime_seconds),
            "status": self.status,
        }

    @classmethod
    def from_redis_hash(cls, data: dict) -> "NetworkMetric":
        """Deserialize from Redis HGETALL response."""
        return cls(
            device_id=data["device_id"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            latency_ms=float(data["latency_ms"]),
            packet_loss_percent=float(data["packet_loss_percent"]),
            bandwidth_utilization_percent=float(data["bandwidth_utilization_percent"]),
            cpu_percent=float(data["cpu_percent"]),
            memory_percent=float(data["memory_percent"]),
            interface_errors_per_min=int(data["interface_errors_per_min"]),
            uptime_seconds=int(data["uptime_seconds"]),
            status=data["status"],
        )
