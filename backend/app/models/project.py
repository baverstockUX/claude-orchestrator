"""Database models for projects."""

from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text
from .task import Base


class ProjectModel(Base):
    """Project database model."""
    __tablename__ = "projects"

    id = Column(String(100), primary_key=True)
    name = Column(String(500), nullable=False)
    description = Column(Text)
    project_path = Column(String(1000), nullable=False)
    status = Column(String(20), default="initializing")  # initializing, running, completed, failed, aborted
    requirements = Column(Text)
    total_tasks = Column(Integer, default=0)
    completed_tasks = Column(Integer, default=0)
    failed_tasks = Column(Integer, default=0)
    max_agents = Column(Integer, default=5)
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
