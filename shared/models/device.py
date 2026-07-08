"""
Shared Pydantic models for Network Devices.
Used by: Network Simulator, Metrics Processor, API Gateway, AI Agent
"""
from enum import Enum
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, Field


class DeviceType(str, Enum):
    """Types of network devices in the system."""
    ROUTER = "ROUTER"
    SWITCH = "SWITCH"
    ACCESS_POINT = "ACCESS_POINT"


class DeviceStatus(str, Enum):
    """Real-time operational status of a device."""
    UP = "UP"               # Fully operational
    DOWN = "DOWN"           # Completely unreachable
    DEGRADED = "DEGRADED"   # Operational but with issues


class Device(BaseModel):
    """
    Represents a network device in the topology.
    Stored in PostgreSQL and Redis for fast lookups.
    """
    device_id: str = Field(..., description="Unique device identifier e.g. R1, S2, AP1")
    device_type: DeviceType
    location: str = Field(..., description="Physical location e.g. DataCenter-Core")
    ip_address: str
    neighbors: List[str] = Field(default_factory=list, description="Directly connected device IDs")
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        use_enum_values = True

    def to_redis_hash(self) -> dict:
        """Serialize device for Redis HSET storage."""
        return {
            "device_id": self.device_id,
            "device_type": self.device_type,
            "location": self.location,
            "ip_address": self.ip_address,
            "neighbors": ",".join(self.neighbors),
        }

    @classmethod
    def from_redis_hash(cls, data: dict) -> "Device":
        """Deserialize device from Redis HGETALL response."""
        data["neighbors"] = data.get("neighbors", "").split(",") if data.get("neighbors") else []
        return cls(**data)
