# Claude Orchestrator

A production-ready multi-agent orchestration system that parallelizes software development work across multiple Claude Sonnet 4.5 instances.

## Overview

Claude Orchestrator enables you to build new projects faster by distributing work across specialized AI agents. Each agent works in its own isolated git worktree, with automatic coordination, conflict prevention, and quality gates.

### Key Features

- **Meta-Agent Task Decomposition**: Uses Claude Sonnet 4.5 to analyze requirements and generate parallelizable task graphs
- **Specialized Worker Agents**: Frontend, Backend, Testing, Docs, Infrastructure, and Integration specialists
- **Git Worktree Isolation**: Each agent works in its own branch with auto-create/cleanup
- **Redis-Based Coordination**: Task queue with dependency management and distributed file locking
- **Quality Gates**: Automated tests, type checking, linting, and security scans before merging
- **Real-Time Monitoring**: CLI and web dashboard with live agent status and progress tracking

## Architecture

```
User Requirements → Meta-Agent (Claude) → Task Graph → Redis Queue
                                                           ↓
                                    ┌──────────────────────┴────────────────────┐
                                    ↓                      ↓                    ↓
                            Frontend Agent          Backend Agent        Testing Agent
                            (worktree-1)            (worktree-2)         (worktree-3)
                                    ↓                      ↓                    ↓
                            Redis File Locks → Quality Gates → Merge Orchestrator
                                                                        ↓
                                                                  Main Branch
```

## Prerequisites

- **Python 3.12** (required)
- **Node.js 18+** and npm (for frontend)
- **Docker** and Docker Compose (for Redis + PostgreSQL)
- **Git**
- **AWS Account** with Bedrock access (Claude Sonnet 4.5 in eu-west-1)

## Quick Start

### 1. Clone and Setup

```bash
cd ~/code/claude-orchestrator
cp .env.example .env
# Edit .env with your AWS credentials
```

### 2. Start Infrastructure

```bash
# Start Redis and PostgreSQL
docker-compose up -d

# Verify services are running
docker-compose ps
```

### 3. Install Python Dependencies

```bash
# Using uv (recommended)
curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync

# Or using pip
python3.12 -m venv venv
source venv/bin/activate
pip install -e .
```

### 4. Initialize Database

```bash
# Run from project root
python -c "import asyncio; from backend.app.database import init_db; asyncio.run(init_db())"
```

### 5. Start API Server (Development)

```bash
uvicorn backend.app.main:app --reload --port 8000
```

Visit http://localhost:8000/docs for API documentation.

## Configuration

Edit `.env` file:

```bash
# Database
DATABASE_URL=postgresql+asyncpg://orch_user:changeme@localhost:5432/orchestrator

# Redis
REDIS_URL=redis://localhost:6379

# AWS Bedrock
AWS_PROFILE=advanced-bedrock
AWS_REGION=eu-west-1
BEDROCK_MODEL_ID=eu.anthropic.claude-sonnet-4-5-20250929-v1:0

# Orchestrator
MAX_AGENTS=5
TASK_TIMEOUT=300
LOCK_TIMEOUT=300
```

## Project Structure

```
claude-orchestrator/
├── backend/
│   ├── app/
│   │   ├── main.py                    # FastAPI application
│   │   ├── config.py                  # Configuration
│   │   ├── database.py                # Database setup
│   │   └── models/                    # SQLAlchemy models
│   ├── orchestrator/
│   │   ├── meta_agent.py              # Task decomposition (TODO)
│   │   ├── worker_agent.py            # Base worker agent (TODO)
│   │   └── specialized_agents/        # Agent implementations (TODO)
│   ├── queue/
│   │   └── redis_queue.py             # Task queue ✓
│   ├── locking/
│   │   └── redis_lock.py              # Distributed locking ✓
│   ├── git/
│   │   ├── worktree_manager.py        # Worktree operations ✓
│   │   └── merge_strategy.py          # Merge logic ✓
│   ├── quality/                       # Quality gates (TODO)
│   ├── llm/                           # Bedrock client (TODO)
│   └── cli/                           # CLI commands (TODO)
└── frontend/                          # Web dashboard (TODO)
```

✓ = Implemented
TODO = Planned

## Development Status

### ✅ Phase 1: Core Infrastructure (COMPLETED)

- [x] Project structure and configuration
- [x] Docker Compose (Redis + PostgreSQL)
- [x] Git worktree manager
- [x] Redis task queue with dependency resolution
- [x] Distributed file locking
- [x] Database models (Task, Agent, Project)
- [x] Basic FastAPI app

**Validation**: Can create/remove worktrees, enqueue/dequeue tasks, acquire/release locks ✓

### 🔄 Phase 2: Meta-Agent (IN PROGRESS)

- [ ] AWS Bedrock client wrapper
- [ ] Meta-agent with task decomposition
- [ ] Dependency graph (DAG) builder
- [ ] Task enqueuing with dependency resolution
- [ ] Unit tests

### 📋 Upcoming Phases

- Phase 3: Worker Agents
- Phase 4: Quality Gates
- Phase 5: Merge Orchestrator
- Phase 6: CLI Interface
- Phase 7: Web Dashboard
- Phase 8: Observability
- Phase 9: Testing & Hardening
- Phase 10: Documentation

See `/Users/christian.baverstock/.claude/plans/fuzzy-moseying-moth.md` for detailed implementation plan.

## Testing Core Components

### Test Worktree Manager

```python
from pathlib import Path
from backend.git.worktree_manager import WorktreeManager

# Initialize
manager = WorktreeManager(Path.cwd())

# Create worktree
worktree_path = manager.create_worktree("agent-1", "main")
print(f"Created: {worktree_path}")

# Commit changes
commit_sha = manager.commit_in_worktree(worktree_path, "Test commit")
print(f"Committed: {commit_sha}")

# Cleanup
manager.remove_worktree(worktree_path)
```

### Test Redis Queue

```python
import asyncio
import redis.asyncio as redis
from backend.queue.redis_queue import RedisQueue, Task

async def test_queue():
    # Connect to Redis
    r = await redis.from_url("redis://localhost:6379")
    queue = RedisQueue(r)

    # Create task
    task = Task(
        id="task_001",
        title="Test task",
        description="This is a test",
        agent_type="frontend",
        project_id="test_project"
    )

    # Enqueue
    await queue.enqueue(task)
    print(f"Enqueued task: {task.id}")

    # Dequeue
    dequeued = await queue.dequeue("frontend", timeout=5)
    if dequeued:
        print(f"Dequeued task: {dequeued.id}")

    await r.close()

asyncio.run(test_queue())
```

### Test Distributed Locking

```python
import asyncio
import redis.asyncio as redis
from backend.locking.redis_lock import RedisLock, LockContext

async def test_lock():
    # Connect to Redis
    r = await redis.from_url("redis://localhost:6379")
    lock_manager = RedisLock(r)

    # Using context manager
    async with LockContext(lock_manager, "file:src/App.vue"):
        print("Lock acquired, doing work...")
        await asyncio.sleep(2)
        print("Work done")
    print("Lock released")

    await r.close()

asyncio.run(test_lock())
```

## Resource Requirements

For 5 concurrent agents:

- **CPU**: 6+ cores
- **Memory**: 8GB+ RAM
- **Disk**: 10GB+ (for worktrees)

Per-agent limits:
- CPU: ~0.4 cores
- Memory: ~800MB
- Task timeout: 5 minutes

## Troubleshooting

### Redis Connection Issues

```bash
# Check Redis is running
docker-compose ps

# Test connection
redis-cli ping
# Should return: PONG
```

### PostgreSQL Connection Issues

```bash
# Check PostgreSQL is running
docker-compose ps

# Test connection
docker exec -it orchestrator-postgres psql -U orch_user -d orchestrator
```

### Git Worktree Issues

```bash
# List all worktrees
git worktree list

# Remove stuck worktrees
git worktree remove .worktrees/agent-1 --force

# Prune orphaned worktrees
git worktree prune
```

## Contributing

This project follows a phased implementation plan. See the plan file for current status and next steps:

```
/Users/christian.baverstock/.claude/plans/fuzzy-moseying-moth.md
```

## License

MIT

## Acknowledgments

Based on the architecture from: [Multi-Agent Orchestration: Running 10+ Claude Instances in Parallel](https://dev.to/bredmond1019/multi-agent-orchestration-running-10-claude-instances-in-parallel-part-3-29da)

Built with:
- [FastAPI](https://fastapi.tiangolo.com/) - Web framework
- [Redis](https://redis.io/) - Task queue and locking
- [PostgreSQL](https://www.postgresql.org/) - Database
- [GitPython](https://gitpython.readthedocs.io/) - Git operations
- [AWS Bedrock](https://aws.amazon.com/bedrock/) - Claude Sonnet 4.5 API
