"""Prompt templates for orchestration."""

from typing import Optional


def get_task_decomposition_prompt(
    requirements: str,
    project_context: Optional[str] = None
) -> str:
    """
    Generate prompt for meta-agent task decomposition.

    Args:
        requirements: User requirements for the project
        project_context: Optional context about existing project

    Returns:
        Formatted prompt for Claude
    """
    context_section = ""
    if project_context:
        context_section = f"""
## Existing Project Context

{project_context}
"""

    return f"""You are a software architect breaking down project requirements into parallelizable tasks for specialized AI agents.

## Requirements

{requirements}
{context_section}

## Your Task

Analyze these requirements and break them into **independent, parallelizable tasks** that can be executed by specialized agents working simultaneously.

### Agent Specializations

- **frontend**: Vue 3 components, Mosaic Design System, TypeScript, UI/UX, styling
- **backend**: FastAPI endpoints, SQLAlchemy models, business logic, APIs
- **testing**: pytest tests, vitest tests, test coverage, integration tests
- **docs**: README files, API documentation, architecture diagrams, user guides
- **infra**: Docker configs, CI/CD pipelines, deployment scripts, environment setup
- **integration**: Third-party API integrations, webhooks, external services

### Task Design Principles

1. **Granularity**: Each task should be 2-4 hours of focused work
2. **Independence**: Tasks should be parallelizable where possible
3. **Dependencies**: Clearly identify which tasks must complete before others
4. **File Specificity**: List exactly which files will be created or modified
5. **Clear Scope**: Each task has a well-defined deliverable

### Output Format

Return a JSON object with this exact structure:

```json
{{
  "project_name": "Brief project name",
  "description": "One-sentence project description",
  "estimated_total_hours": 20,
  "tasks": [
    {{
      "id": "task_001",
      "title": "Create Express API server scaffold",
      "description": "Set up basic Express.js server with middleware, error handling, and routing structure",
      "agent_type": "backend",
      "estimated_hours": 2.0,
      "files_to_create": ["src/server.js", "src/routes/index.js", "src/middleware/errorHandler.js"],
      "files_to_modify": ["package.json"],
      "dependencies": []
    }},
    {{
      "id": "task_002",
      "title": "Implement user authentication API",
      "description": "Create login/register endpoints with JWT token generation",
      "agent_type": "backend",
      "estimated_hours": 3.0,
      "files_to_create": ["src/routes/auth.js", "src/controllers/authController.js"],
      "files_to_modify": ["src/routes/index.js"],
      "dependencies": ["task_001"]
    }},
    {{
      "id": "task_003",
      "title": "Build login UI component",
      "description": "Create Vue 3 login form with Mosaic Design System components",
      "agent_type": "frontend",
      "estimated_hours": 2.5,
      "files_to_create": ["src/components/LoginForm.vue", "src/components/LoginPage.vue"],
      "files_to_modify": ["src/router/index.ts"],
      "dependencies": ["task_002"]
    }}
  ]
}}
```

### Critical Rules

1. Task IDs must be unique (task_001, task_002, etc.)
2. Dependencies must reference valid task IDs
3. Avoid circular dependencies (task A depends on task B depends on task A)
4. Group related work into single tasks (don't split unnecessarily)
5. Consider the natural order of development (backend before frontend, models before endpoints, etc.)
6. Ensure tasks can actually be done in parallel where dependencies allow

Generate the complete task breakdown now."""


def get_worker_agent_prompt(
    task_title: str,
    task_description: str,
    agent_type: str,
    files_to_create: list[str],
    files_to_modify: list[str],
    project_context: Optional[str] = None
) -> str:
    """
    Generate prompt for worker agent task execution.

    Args:
        task_title: Title of the task
        task_description: Detailed description
        agent_type: Type of agent (frontend, backend, etc.)
        files_to_create: List of files to create
        files_to_modify: List of files to modify
        project_context: Optional existing file contents

    Returns:
        Formatted prompt for Claude
    """
    agent_guidance = {
        "frontend": """
You are a frontend specialist expert in:
- Vue 3 Composition API
- TypeScript
- Mosaic Design System components
- Responsive design
- Accessibility (WCAG 2.1)
- Modern CSS (Flexbox, Grid)

Focus on creating clean, reusable components with proper TypeScript types and MDS components.""",

        "backend": """
You are a backend specialist expert in:
- FastAPI (async/await patterns)
- SQLAlchemy ORM
- RESTful API design
- Authentication & authorization
- Error handling
- Input validation with Pydantic

Focus on creating robust, well-structured APIs with proper error handling and validation.""",

        "testing": """
You are a testing specialist expert in:
- pytest for Python
- vitest for TypeScript/Vue
- Test coverage analysis
- Integration testing
- Mocking and fixtures
- Edge case identification

Focus on comprehensive test coverage with clear, maintainable test code.""",

        "docs": """
You are a documentation specialist expert in:
- Technical writing
- API documentation
- Architecture diagrams (Mermaid)
- User guides
- README structure
- Code comments

Focus on clear, comprehensive documentation that helps developers understand and use the code.""",

        "infra": """
You are an infrastructure specialist expert in:
- Docker and Docker Compose
- CI/CD pipelines (GitHub Actions)
- Environment configuration
- Deployment automation
- Security best practices

Focus on creating maintainable, secure infrastructure configurations.""",

        "integration": """
You are an integration specialist expert in:
- REST API integration
- Webhook handling
- OAuth flows
- Error handling for external services
- Rate limiting
- Retry logic

Focus on robust integrations with proper error handling and resilience."""
    }

    context_section = ""
    if project_context:
        context_section = f"""
## Existing Project Context

{project_context}
"""

    return f"""# Task Assignment

{agent_guidance.get(agent_type, "")}

## Your Task

**Title**: {task_title}

**Description**: {task_description}

**Files to Create**:
{chr(10).join(f"- {f}" for f in files_to_create) if files_to_create else "- None"}

**Files to Modify**:
{chr(10).join(f"- {f}" for f in files_to_modify) if files_to_modify else "- None"}
{context_section}

## Instructions

1. Implement the complete solution for this task
2. Write clean, well-documented code
3. Follow best practices for {agent_type} development
4. Include error handling where appropriate
5. Add comments for complex logic

## Output Format

Provide the complete implementation with:

1. All file contents (use clear headings for each file)
2. Any installation commands needed (npm install, pip install)
3. Brief explanation of key implementation decisions

Format each file like this:

```
## File: path/to/file.ext

[Complete file contents here]
```

Begin your implementation now."""


def get_frontend_agent_prompt(task, existing_files: dict[str, str]) -> str:
    """Generate prompt for FrontendAgent."""
    context = ""
    if existing_files:
        context = "\n## Existing Files to Modify\n\n"
        for path, content in existing_files.items():
            context += f"### {path}\n```\n{content}\n```\n\n"

    return f"""# Frontend Task

## Task Details
**ID**: {task.id}
**Title**: {task.title}
**Description**: {task.description}

## Files to Create
{chr(10).join(f"- {f}" for f in task.files_to_create) if task.files_to_create else "- None"}

## Files to Modify
{chr(10).join(f"- {f}" for f in task.files_to_modify) if task.files_to_modify else "- None"}
{context}

## Instructions

Implement this Vue 3 + Mosaic Design System task. Follow these guidelines:

1. Use Vue 3 Composition API with `<script setup lang="ts">`
2. Use Mosaic Design System components (mds-button, mds-input, mds-card, etc.)
3. Write TypeScript with proper type definitions
4. Follow Vue style guide and MDS patterns
5. Ensure responsive design and accessibility

## Output Format

For each file, use this format:

```vue
<!-- filepath: src/components/MyComponent.vue -->
<template>
  <div>
    <!-- Component template -->
  </div>
</template>

<script setup lang="ts">
// Component logic
</script>

<style scoped>
/* Component styles */
</style>
```

Provide complete, production-ready code for all files."""


def get_backend_agent_prompt(task, existing_files: dict[str, str]) -> str:
    """Generate prompt for BackendAgent."""
    context = ""
    if existing_files:
        context = "\n## Existing Files to Modify\n\n"
        for path, content in existing_files.items():
            context += f"### {path}\n```python\n{content}\n```\n\n"

    return f"""# Backend Task

## Task Details
**ID**: {task.id}
**Title**: {task.title}
**Description**: {task.description}

## Files to Create
{chr(10).join(f"- {f}" for f in task.files_to_create) if task.files_to_create else "- None"}

## Files to Modify
{chr(10).join(f"- {f}" for f in task.files_to_modify) if task.files_to_modify else "- None"}
{context}

## Instructions

Implement this FastAPI backend task. Follow these guidelines:

1. Use async/await patterns for FastAPI endpoints
2. Use SQLAlchemy 2.0+ async patterns for database
3. Use Pydantic v2 for request/response models
4. Include proper error handling with HTTPException
5. Add input validation and proper status codes
6. Follow RESTful API conventions

## Output Format

For each file, use this format:

```python
# filepath: backend/api/routes.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

# Implementation code here
```

Provide complete, production-ready code for all files."""


def get_testing_agent_prompt(task, existing_files: dict[str, str]) -> str:
    """Generate prompt for TestingAgent."""
    context = ""
    if existing_files:
        context = "\n## Files to Test\n\n"
        for path, content in existing_files.items():
            context += f"### {path}\n```\n{content}\n```\n\n"

    return f"""# Testing Task

## Task Details
**ID**: {task.id}
**Title**: {task.title}
**Description**: {task.description}

## Files to Create
{chr(10).join(f"- {f}" for f in task.files_to_create) if task.files_to_create else "- None"}

## Files to Modify
{chr(10).join(f"- {f}" for f in task.files_to_modify) if task.files_to_modify else "- None"}
{context}

## Instructions

Write comprehensive tests for this task. Follow these guidelines:

1. For Python: Use pytest with async support, fixtures, and parametrize
2. For TypeScript/Vue: Use vitest with Vue Test Utils
3. Include unit tests for all functions/methods
4. Include integration tests for API endpoints
5. Test edge cases and error scenarios
6. Aim for high coverage (>80%)
7. Use clear test names that describe what's being tested

## Output Format

For each test file, use this format:

```python
# filepath: tests/test_something.py
import pytest

def test_something():
    # Test implementation
    pass
```

Or for TypeScript:

```typescript
# filepath: tests/something.test.ts
import { describe, it, expect } from 'vitest'

describe('Something', () => {{
  it('should do something', () => {{
    // Test implementation
  }})
}})
```

Provide complete test coverage for all functionality."""


def get_docs_agent_prompt(task, existing_files: dict[str, str]) -> str:
    """Generate prompt for DocsAgent."""
    context = ""
    if existing_files:
        context = "\n## Existing Files (for context)\n\n"
        for path, content in existing_files.items():
            context += f"### {path}\n```\n{content[:500]}...\n```\n\n"

    return f"""# Documentation Task

## Task Details
**ID**: {task.id}
**Title**: {task.title}
**Description**: {task.description}

## Files to Create
{chr(10).join(f"- {f}" for f in task.files_to_create) if task.files_to_create else "- None"}

## Files to Modify
{chr(10).join(f"- {f}" for f in task.files_to_modify) if task.files_to_modify else "- None"}
{context}

## Instructions

Write clear, comprehensive documentation. Follow these guidelines:

1. Use proper Markdown formatting
2. Include code examples where relevant
3. Structure content with clear headings
4. Add table of contents for longer docs
5. Use Mermaid diagrams for architecture
6. Keep language clear and concise
7. Include setup/installation instructions

## Output Format

For each documentation file:

```markdown
<!-- filepath: README.md -->
# Project Title

Clear, comprehensive documentation here...
```

Provide complete documentation that helps developers understand and use the code."""


def get_infra_agent_prompt(task, existing_files: dict[str, str]) -> str:
    """Generate prompt for InfraAgent."""
    context = ""
    if existing_files:
        context = "\n## Existing Files to Modify\n\n"
        for path, content in existing_files.items():
            context += f"### {path}\n```\n{content}\n```\n\n"

    return f"""# Infrastructure Task

## Task Details
**ID**: {task.id}
**Title**: {task.title}
**Description**: {task.description}

## Files to Create
{chr(10).join(f"- {f}" for f in task.files_to_create) if task.files_to_create else "- None"}

## Files to Modify
{chr(10).join(f"- {f}" for f in task.files_to_modify) if task.files_to_modify else "- None"}
{context}

## Instructions

Create infrastructure configuration files. Follow these guidelines:

1. For Dockerfiles: Use multi-stage builds, minimize image size
2. For CI/CD: Use GitHub Actions with proper caching
3. For configs: Use environment variables for secrets
4. Include health checks and proper logging
5. Follow security best practices (no hardcoded secrets)
6. Add comments explaining configuration choices

## Output Format

For each configuration file:

```yaml
# filepath: .github/workflows/ci.yml
name: CI Pipeline

# Configuration here
```

Or for Dockerfiles:

```dockerfile
# filepath: Dockerfile
FROM python:3.12-slim

# Dockerfile content
```

Provide production-ready infrastructure configurations."""


def get_integration_agent_prompt(task, existing_files: dict[str, str]) -> str:
    """Generate prompt for IntegrationAgent."""
    context = ""
    if existing_files:
        context = "\n## Existing Files to Modify\n\n"
        for path, content in existing_files.items():
            context += f"### {path}\n```\n{content}\n```\n\n"

    return f"""# Integration Task

## Task Details
**ID**: {task.id}
**Title**: {task.title}
**Description**: {task.description}

## Files to Create
{chr(10).join(f"- {f}" for f in task.files_to_create) if task.files_to_create else "- None"}

## Files to Modify
{chr(10).join(f"- {f}" for f in task.files_to_modify) if task.files_to_modify else "- None"}
{context}

## Instructions

Implement third-party API integration. Follow these guidelines:

1. Use proper authentication (API keys, OAuth, etc.)
2. Include comprehensive error handling
3. Implement retry logic with exponential backoff
4. Handle rate limiting properly
5. Add request/response logging
6. Use environment variables for credentials
7. Include timeout configuration
8. Validate responses and handle errors gracefully

## Output Format

For each file:

```python
# filepath: backend/integrations/stripe.py
import httpx
from typing import Optional

# Integration implementation
```

Or for TypeScript:

```typescript
# filepath: src/services/stripe.ts
import Stripe from 'stripe'

// Integration implementation
```

Provide robust, production-ready integration code."""
