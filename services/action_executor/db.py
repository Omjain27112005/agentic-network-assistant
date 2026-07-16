"""
Database Layer — SQLAlchemy ORM for PostgreSQL.

Handles all persistent storage for incidents and agent actions.
Uses synchronous SQLAlchemy (not async) because:
- Our Kafka consumer is single-threaded synchronous
- Simpler code without async complexity
- Connection pooling handles performance

Production features:
- Connection pool with pre-ping (detect stale connections)
- Retry on connection failure at startup
- Context manager for session lifecycle
- Explicit transaction management
- Structured logging for every DB operation
"""
import time
import logging
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Optional, Generator

import structlog
from sqlalchemy import (
    create_engine,
    text,
    Column, Integer, String, Float, Boolean, Text, DateTime, JSON,
)
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from sqlalchemy.exc import OperationalError, SQLAlchemyError

logger = structlog.get_logger(__name__)

Base = declarative_base()


# -----------------------------------------------
# ORM Models (mirror of database/init.sql tables)
# -----------------------------------------------

class IncidentORM(Base):
    """ORM model for the incidents table."""
    __tablename__ = "incidents"

    id               = Column(Integer, primary_key=True, autoincrement=True)
    alert_id         = Column(String(36), nullable=False, unique=True)
    device_id        = Column(String(10), nullable=False)
    alert_type       = Column(String(50), nullable=False)
    severity         = Column(String(20), nullable=False)
    root_cause       = Column(Text, nullable=True)
    confidence_score = Column(Float, nullable=True)
    recommendation   = Column(Text, nullable=True)
    jira_ticket_id   = Column(String(20), nullable=True)
    resolved         = Column(Boolean, default=False)
    created_at       = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    resolved_at      = Column(DateTime(timezone=True), nullable=True)
    raw_alert        = Column(JSON, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<Incident id={self.id} device={self.device_id} "
            f"type={self.alert_type} severity={self.severity}>"
        )


class AgentActionORM(Base):
    """ORM model for the agent_actions table."""
    __tablename__ = "agent_actions"

    id             = Column(Integer, primary_key=True, autoincrement=True)
    incident_id    = Column(Integer, nullable=True)     # FK to incidents.id
    action_type    = Column(String(50), nullable=False)  # CREATE_TICKET | LOG | NOTIFY
    action_payload = Column(JSON, nullable=True)
    success        = Column(Boolean, default=True)
    error_message  = Column(Text, nullable=True)
    executed_at    = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    def __repr__(self) -> str:
        return f"<AgentAction id={self.id} type={self.action_type} success={self.success}>"


# -----------------------------------------------
# Database Engine + Session Factory
# -----------------------------------------------

class Database:
    """
    Database connection manager with connection pooling and retry.

    Usage:
        db = Database(database_url)
        with db.session() as session:
            session.add(incident)
            session.commit()
    """

    MAX_CONNECT_RETRIES = 5
    CONNECT_RETRY_BACKOFF = 3.0  # seconds between retries

    def __init__(self, database_url: str):
        self._engine = create_engine(
            database_url,
            pool_size=5,                # Maintain 5 persistent connections
            max_overflow=10,            # Allow 10 extra connections under load
            pool_pre_ping=True,         # Test connection before use (detects stale)
            pool_recycle=3600,          # Recycle connections every 1 hour
            echo=False,                 # Set True to log all SQL queries (debug only)
        )
        self._SessionFactory = sessionmaker(
            bind=self._engine,
            autocommit=False,
            autoflush=False,
        )
        self._connect_with_retry()
        logger.info("database.connected", url=database_url.split("@")[-1])  # Log host only, not creds

    def _connect_with_retry(self) -> None:
        """Retry connection on startup — DB container may not be ready yet."""
        for attempt in range(self.MAX_CONNECT_RETRIES):
            try:
                with self._engine.connect() as conn:
                    conn.execute(text("SELECT 1"))
                logger.info("database.connection_verified", attempt=attempt + 1)
                return
            except OperationalError as e:
                wait = self.CONNECT_RETRY_BACKOFF * (attempt + 1)
                logger.warning(
                    "database.connection_retry",
                    attempt=attempt + 1,
                    max_attempts=self.MAX_CONNECT_RETRIES,
                    wait_seconds=wait,
                    error=str(e)[:100],
                )
                time.sleep(wait)

        raise RuntimeError(
            f"Could not connect to PostgreSQL after {self.MAX_CONNECT_RETRIES} attempts."
        )

    @contextmanager
    def session(self) -> Generator[Session, None, None]:
        """
        Context manager for database sessions.
        Automatically commits on success, rolls back on exception.

        Usage:
            with db.session() as s:
                s.add(incident_orm)
                # commit happens automatically
        """
        session: Session = self._SessionFactory()
        try:
            yield session
            session.commit()
        except SQLAlchemyError as e:
            session.rollback()
            logger.error("database.transaction_rolled_back", error=str(e))
            raise
        finally:
            session.close()

    def dispose(self) -> None:
        """Close all connections in the pool (called on shutdown)."""
        self._engine.dispose()
        logger.info("database.disposed")


# -----------------------------------------------
# Repository Functions
# (Business logic for DB operations lives here, not in models)
# -----------------------------------------------

def save_incident(
    db: Database,
    agent_result: dict,
    alert_data: dict,
    jira_ticket_id: Optional[str] = None,
) -> Optional[int]:
    """
    Save a new incident record to PostgreSQL.

    Args:
        db: Database instance
        agent_result: AgentResult dict from Kafka
        alert_data: Original alert dict
        jira_ticket_id: Jira ticket ID if created (e.g. "NET-1042")

    Returns:
        The new incident's auto-generated integer ID, or None on failure
    """
    try:
        incident = IncidentORM(
            alert_id=agent_result.get("alert_id", "UNKNOWN"),
            device_id=agent_result.get("device_id", "UNKNOWN"),
            alert_type=alert_data.get("alert_type", "UNKNOWN"),
            severity=alert_data.get("severity", "CRITICAL"),
            root_cause=agent_result.get("root_cause"),
            confidence_score=float(agent_result.get("confidence_score", 0.0)),
            recommendation=agent_result.get("immediate_action"),
            jira_ticket_id=jira_ticket_id,
            resolved=False,
            raw_alert=alert_data,  # Store full alert JSON for audit
        )

        with db.session() as session:
            session.add(incident)
            session.flush()  # Get the auto-generated ID before commit
            incident_id = incident.id

        logger.info(
            "incident.saved",
            incident_id=incident_id,
            device_id=incident.device_id,
            alert_type=incident.alert_type,
            jira_ticket=jira_ticket_id,
        )
        return incident_id

    except SQLAlchemyError as e:
        logger.error("incident.save_failed", error=str(e), alert_id=agent_result.get("alert_id"))
        return None


def save_agent_action(
    db: Database,
    incident_id: Optional[int],
    action_type: str,
    action_payload: dict,
    success: bool = True,
    error_message: Optional[str] = None,
) -> None:
    """
    Save an audit log entry for an action taken by the AI Agent.

    Every action (ticket creation, notification, etc.) is logged here.
    This provides full traceability: who did what, when, and whether it succeeded.
    """
    try:
        action = AgentActionORM(
            incident_id=incident_id,
            action_type=action_type,
            action_payload=action_payload,
            success=success,
            error_message=error_message,
        )

        with db.session() as session:
            session.add(action)

        logger.info(
            "agent_action.saved",
            action_type=action_type,
            incident_id=incident_id,
            success=success,
        )

    except SQLAlchemyError as e:
        logger.error("agent_action.save_failed", action_type=action_type, error=str(e))


def get_recent_incidents(db: Database, limit: int = 50) -> list:
    """Fetch the most recent incidents for API Gateway to serve."""
    try:
        with db.session() as session:
            results = (
                session.query(IncidentORM)
                .order_by(IncidentORM.created_at.desc())
                .limit(limit)
                .all()
            )
            return [
                {
                    "id": r.id,
                    "alert_id": r.alert_id,
                    "device_id": r.device_id,
                    "alert_type": r.alert_type,
                    "severity": r.severity,
                    "root_cause": r.root_cause,
                    "confidence_score": r.confidence_score,
                    "recommendation": r.recommendation,
                    "jira_ticket_id": r.jira_ticket_id,
                    "resolved": r.resolved,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                    "resolved_at": r.resolved_at.isoformat() if r.resolved_at else None,
                }
                for r in results
            ]
    except SQLAlchemyError as e:
        logger.error("incidents.fetch_failed", error=str(e))
        return []
