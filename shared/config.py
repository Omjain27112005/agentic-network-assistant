"""
Centralized config — reads from environment variables.
All services import from here. Never hardcode values in service files.
"""
import os
from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    Pydantic validates types automatically — fails fast on misconfiguration.
    """

    # --- Kafka ---
    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_topic_metrics: str = "network.metrics"
    kafka_topic_alerts: str = "network.alerts"
    kafka_topic_actions: str = "network.actions"
    kafka_topic_incidents: str = "network.incidents"

    # --- Redis ---
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_ttl_metrics: int = 60
    redis_ttl_alerts: int = 3600

    # --- PostgreSQL ---
    database_url: str = "postgresql://postgres:postgres@localhost:5432/network_assistant"

    # --- Groq LLM ---
    groq_api_key: str = ""
    groq_model: str = "llama3-70b-8192"

    # --- Jira ---
    jira_base_url: str = ""
    jira_email: str = ""
    jira_api_token: str = ""
    jira_project_key: str = "NET"

    # --- FastAPI ---
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_reload: bool = True
    cors_origins: str = "http://localhost:5173"

    # --- Network Simulator ---
    simulator_interval_seconds: int = 5
    simulator_device_count: int = 10
    anomaly_injection_rate: float = 0.05

    # --- Logging ---
    log_level: str = "INFO"
    log_format: str = "json"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False

    @property
    def cors_origins_list(self) -> list:
        """Parse comma-separated CORS origins into a list."""
        return [origin.strip() for origin in self.cors_origins.split(",")]


@lru_cache()
def get_settings() -> Settings:
    """
    Cached settings singleton.
    @lru_cache ensures Settings() is only called once per process.
    """
    return Settings()
