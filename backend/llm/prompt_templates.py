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
