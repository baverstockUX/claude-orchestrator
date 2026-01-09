# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Claude Orchestrator is a multi-agent orchestration system that parallelizes software development across multiple Claude Sonnet 4.5 instances. Each agent works in an isolated git worktree with automatic coordination via Redis-based task queuing and distributed file locking.

**Current Status**: Phases 1-3 complete (Core Infrastructure, Meta-Agent, Worker Agents). See PHASE2_RESULTS.md and PHASE3_RESULTS.md for details.

## Core Architecture

### 1. Task Flow
```
User Requirements
  → MetaAgent (analyzes & decomposes via Claude Sonnet 4.5)
  → DependencyGraph (builds DAG, detects cycles)
  → RedisQueue (enqueues tasks by dependency order)
  → WorkerAgents (poll queue by specialization)
  → Execute in isolated git worktrees
  → Commit with proper metadata
  → Report completion (triggers dependent tasks)
```

### 2. Agent Specializations
Six agent types with specialized prompts and parsing logic:
- **FrontendAgent**: Vue 3 + Mosaic Design System, parses `<!-- filepath: ... -->` and ```vue blocks
- **BackendAgent**: FastAPI + SQLAlchemy, parses `# filepath: ...` and ```python blocks
- **TestingAgent**: pytest/vitest, parses test files with same patterns
- **DocsAgent**: Technical documentation, parses markdown with filepath markers
- **InfraAgent**: Docker/CI/CD configs, parses YAML/Dockerfile blocks
- **IntegrationAgent**: Third-party APIs, parses integration code

Each agent inherits from `WorkerAgent` base class and implements:
- `_invoke_llm_for_task()`: Generate agent-specific prompt and call Claude
- `_apply_changes()`: Parse LLM response for filepath markers and code blocks

### 3. Git Worktree Isolation
Each agent spawns with its own worktree:
- Branch naming: `agent-{agent_id}` (e.g., `agent-backend-001`)
- Worktrees stored in `.worktrees/` directory
- Auto-detects base branch (defaults to repo's active branch or "main")
- Commits have author: `Agent-{type} <agent-{id}@orchestrator.local>`

### 4. Distributed Locking (Redis)
Prevents file conflicts when multiple agents work in parallel:
- Lock pattern: `file:{relative_path}` (e.g., `file:src/App.vue`)
- Acquired before file modifications, released in finally blocks
- Uses exponential backoff on contention
- Auto-expires after task_timeout (default 5 min)

### 5. Dependency Resolution
`DependencyGraph` class manages task ordering:
- Builds DAG from task dependencies
- Validates no circular dependencies (raises error if found)
- `get_execution_order()`: Returns list of levels for parallel execution
- `get_critical_path()`: Calculates minimum completion time
- `mark_completed()`: Auto-enqueues dependent tasks when ready

## Common Commands

### Testing

```bash
# Test worktree operations (no AWS/Redis required)
python3 test_worktree.py

# Test meta-agent task decomposition (requires AWS Bedrock)
python3 test_meta_agent.py

# Test worker agent with real LLM execution (requires AWS Bedrock)
python3 test_worker_agent.py
```

### Development

```bash
# Run type checking
mypy backend/

# Run linter
ruff check backend/

# Format code
ruff format backend/

# Start FastAPI server with auto-reload
uvicorn backend.app.main:app --reload --port 8000
```

### Infrastructure

**Note**: User does not have Docker license. Infrastructure commands are for reference only.

```bash
# Start Redis + PostgreSQL (if Docker available)
docker-compose up -d

# Check service status
docker-compose ps

# View logs
docker-compose logs -f redis
docker-compose logs -f postgres

# Stop services
docker-compose down
```

## Critical Implementation Details

### Import Ordering (CRITICAL)
To avoid import conflicts between gitpython package and `backend.git` module:

```python
# ALWAYS import gitpython BEFORE backend modules
import git as gitpython_module

# Then import backend modules
from backend.git.worktree_manager import WorktreeManager
```

This pattern is used in all test files. See test_worktree.py:7-11 for reference.

### AWS Bedrock Configuration
Claude Sonnet 4.5 via AWS Bedrock requires specific configuration:

```python
BedrockClient(
    profile="advanced-bedrock",  # User's AWS profile
    region="eu-west-1",
    model_id="eu.anthropic.claude-sonnet-4-5-20250929-v1:0"
)
```

**Important**: Claude 4.5 does NOT support both `temperature` and `top_p` simultaneously. Only use `temperature`.

### LLM Response Parsing
Each specialized agent expects specific filepath markers:

**Frontend (Vue/TS)**:
```vue
<!-- filepath: src/components/MyComponent.vue -->
<template>...</template>
```

**Backend (Python)**:
```python
# filepath: backend/api/routes.py
from fastapi import APIRouter
```

**Docs (Markdown)**:
```markdown
<!-- filepath: README.md -->
# Project Title
```

If no filepath markers found, agent falls back to `task.files_to_create[0]` if only one file expected.

### Worker Agent Lifecycle

```python
# 1. Spawn worktree
await agent.spawn()  # Creates .worktrees/agent-{id}

# 2. Execute task
result = await agent._execute_task(task)
# - Acquires locks on all files_to_create + files_to_modify
# - Invokes Claude with agent-specific prompt
# - Parses response for filepath markers
# - Writes files (creates parent dirs automatically)
# - Commits with task title/description as message
# - Releases locks (even on error via finally block)

# 3. Cleanup
await agent.cleanup()  # Removes worktree
```

### Dependency Graph Validation
When adding tasks to graph, always validate:

```python
graph = DependencyGraph()
for task in tasks:
    graph.add_node(TaskNode(...))

# CRITICAL: Validate before execution
is_valid, cycle = graph.validate_acyclic()
if not is_valid:
    raise ValueError(f"Circular dependency: {' -> '.join(cycle)}")
```

## File Structure Context

### Backend Architecture
- `backend/llm/`: Bedrock client and prompt templates
- `backend/orchestrator/`: Meta-agent, worker agents, dependency graph
- `backend/queue/`: Redis task queue with dependency resolution
- `backend/locking/`: Distributed file locking via Redis
- `backend/git/`: Worktree manager and merge strategies
- `backend/app/`: FastAPI application and database models

### Key Classes
- `MetaAgent`: Analyzes requirements → generates task graph via Claude
- `WorkerAgent`: Base class for all specialized agents (abstract)
- `DependencyGraph`: DAG with cycle detection and topological sort
- `RedisQueue`: Task queue with FIFO semantics per agent type
- `RedisLock`: Distributed locking with exponential backoff
- `WorktreeManager`: Git worktree create/commit/cleanup operations

### Database Models
- `TaskModel`: Task state (pending/in_progress/completed/failed)
- `AgentModel`: Agent heartbeats and status
- `ProjectModel`: Top-level orchestration state

## AWS Bedrock Integration

User has AWS profile `advanced-bedrock` configured with access to Claude Sonnet 4.5 in `eu-west-1`.

**Model invocation pattern**:
```python
response = bedrock.invoke_model(
    prompt=prompt,
    system_prompt="You are an expert...",
    max_tokens=8000
)
# response.content contains text
# response.usage contains token counts
```

**JSON schema responses**:
```python
response_data = bedrock.invoke_model_with_json_schema(
    prompt=prompt,
    json_schema={"field": "type", ...},
    system_prompt="You are an expert..."
)
# Automatically parses JSON from markdown code blocks
```

## Known Issues & Gotchas

1. **Default branch naming**: New git repos default to "master" (not "main"). WorkerAgent.spawn() auto-detects active branch.

2. **BedrockResponse.usage field**: Must be `dict[str, Any]` not `dict[str, int]` because AWS returns nested dicts for cache metrics.

3. **Gitpython path handling**: Use relative paths for `repo.index.add()`, not absolute paths.

4. **Lock timeout**: If task execution exceeds 5 minutes, locks auto-expire. Increase `task_timeout` for long-running tasks.

5. **File markers required**: LLM responses MUST include filepath markers unless task creates exactly one file (fallback case).

## Next Phase: Quality Gates

Phase 4 will implement validation pipeline before merging agent work:
- Syntax validation (pyflakes, tsc)
- Type checking (mypy, tsc --noEmit)
- Linting (ruff, eslint)
- Test execution (pytest, vitest)
- Security scanning (detect secrets)

See implementation plan at: `/Users/christian.baverstock/.claude/plans/fuzzy-moseying-moth.md`
