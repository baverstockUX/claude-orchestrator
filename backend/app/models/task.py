"""Database models for tasks."""

from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, Column, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all models."""
    pass


class TaskModel(Base):
    """Task database model."""
    __tablename__ = "tasks"

    id = Column(String(100), primary_key=True)
    project_id = Column(String(100), index=True, nullable=False)
    title = Column(String(500), nullable=False)
    description = Column(Text)
    agent_type = Column(String(50), index=True, nullable=False)
    files_to_create = Column(JSON)
    files_to_modify = Column(JSON)
    dependencies = Column(JSON)
    estimated_hours = Column(Float, default=2.0)
    status = Column(String(20), index=True, default="pending")  # pending, in_progress, completed, failed
    result_data = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    agent_id = Column(String(100))
    commit_sha = Column(String(40))
    error_message = Column(Text)
