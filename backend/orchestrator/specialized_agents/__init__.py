"""Specialized worker agents for different task types."""

from backend.orchestrator.specialized_agents.frontend_agent import FrontendAgent
from backend.orchestrator.specialized_agents.backend_agent import BackendAgent
from backend.orchestrator.specialized_agents.testing_agent import TestingAgent
from backend.orchestrator.specialized_agents.docs_agent import DocsAgent
from backend.orchestrator.specialized_agents.infra_agent import InfraAgent
from backend.orchestrator.specialized_agents.integration_agent import IntegrationAgent

__all__ = [
    "FrontendAgent",
    "BackendAgent",
    "TestingAgent",
    "DocsAgent",
    "InfraAgent",
    "IntegrationAgent",
]
