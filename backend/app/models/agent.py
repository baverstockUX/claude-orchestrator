"""Database models for agents."""

from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String
from .task import Base


class AgentModel(Base):
    """Agent database model."""
    __tablename__ = "agents"

    id = Column(String(100), primary_key=True)
    project_id = Column(String(100), index=True, nullable=False)
    agent_type = Column(String(50), nullable=False)  # frontend, backend, testing, docs, etc.
    status = Column(String(20), default="idle")  # idle, busy, error
    current_task_id = Column(String(100))
    worktree_path = Column(String(500))
    branch_name = Column(String(200))
    tasks_completed = Column(Integer, default=0)
    tasks_failed = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_heartbeat = Column(DateTime)
