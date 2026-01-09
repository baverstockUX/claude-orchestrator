"""Test script for MetaAgent with AWS Bedrock."""

import json
import sys
from pathlib import Path

# Import gitpython first
import git as gitpython_module

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from backend.llm.bedrock_client import BedrockClient
from backend.orchestrator.meta_agent import MetaAgent

def test_meta_agent():
    """Test meta-agent task decomposition."""
    print("=" * 70)
    print("Testing MetaAgent with Claude Sonnet 4.5")
    print("=" * 70)

    # Sample requirements
    requirements = """
Build a todo application with the following features:

Frontend (Vue 3 + Mosaic Design System):
- Todo list display with checkboxes
- Add new todo input form
- Delete todo button
- Filter by status (all/active/completed)
- Responsive design

Backend (FastAPI):
- REST API for todos (CRUD operations)
- SQLAlchemy models for todos
- Input validation
- Error handling

Testing:
- Unit tests for API endpoints
- Frontend component tests

Documentation:
- README with setup instructions
- API documentation
    """

    try:
        # Initialize Bedrock client
        print("\n1. Initializing AWS Bedrock client...")
        bedrock = BedrockClient(
            profile="advanced-bedrock",
            region="eu-west-1"
        )
        print("   ✓ Bedrock client initialized")

        # Initialize meta-agent
        print("\n2. Initializing MetaAgent...")
        meta_agent = MetaAgent(bedrock)
        print("   ✓ MetaAgent initialized")

        # Analyze requirements
        print("\n3. Analyzing requirements with Claude Sonnet 4.5...")
        print(f"   Requirements: {requirements[:100]}...")

        project_plan = meta_agent.analyze_requirements(
            requirements=requirements,
            project_id="test_todo_app"
        )

        print(f"\n   ✓ Generated project plan:")
        print(f"     Project: {project_plan.project_name}")
        print(f"     Description: {project_plan.description}")
        print(f"     Total tasks: {len(project_plan.tasks)}")
        print(f"     Estimated hours: {project_plan.estimated_total_hours}")

        # Display tasks
        print(f"\n4. Task Breakdown:")
        for task in project_plan.tasks:
            deps_str = f" (depends on: {', '.join(task.dependencies)})" if task.dependencies else ""
            print(f"\n   [{task.id}] {task.title}")
            print(f"   Type: {task.agent_type} | Hours: {task.estimated_hours}{deps_str}")
            print(f"   Files to create: {', '.join(task.files_to_create[:3])}{'...' if len(task.files_to_create) > 3 else ''}")

        # Build dependency graph
        print(f"\n5. Building dependency graph...")
        graph = meta_agent.create_dependency_graph(project_plan)
        print(f"   ✓ Graph created and validated (no circular dependencies)")

        # Get execution plan
        print(f"\n6. Generating execution plan...")
        execution_plan = meta_agent.get_execution_plan(graph)

        print(f"\n   Execution Strategy:")
        print(f"   - Total levels: {execution_plan['total_levels']}")
        print(f"   - Sequential time: {execution_plan['statistics']['sequential_hours']:.1f}h")
        print(f"   - Parallel time: {execution_plan['statistics']['parallel_hours']:.1f}h")
        print(f"   - Speedup: {execution_plan['statistics']['speedup_factor']:.1f}x")

        print(f"\n   Execution Levels (parallel execution plan):")
        for level_info in execution_plan['levels']:
            print(f"   Level {level_info['level_number']}: {level_info['parallel_tasks']} tasks in parallel ({level_info['estimated_hours']:.1f}h)")
            for task_id in level_info['task_ids']:
                task = next(t for t in project_plan.tasks if t.id == task_id)
                print(f"     - {task_id}: {task.title} ({task.agent_type})")

        # Critical path
        critical_path = execution_plan['critical_path']
        print(f"\n   Critical Path ({critical_path['total_hours']:.1f}h):")
        for task_id in critical_path['task_ids']:
            task = next(t for t in project_plan.tasks if t.id == task_id)
            print(f"     → {task_id}: {task.title}")

        # Get initial tasks
        print(f"\n7. Identifying initial tasks (ready to start)...")
        initial_tasks = meta_agent.get_initial_tasks(graph)
        print(f"   ✓ {len(initial_tasks)} tasks can start immediately:")
        for task_node in initial_tasks:
            print(f"     - {task_node.task_id}: {task_node.title} ({task_node.agent_type})")

        print("\n" + "=" * 70)
        print("✅ ALL META-AGENT TESTS PASSED")
        print("=" * 70)

        # Save results
        results_file = Path(__file__).parent / "meta_agent_test_results.json"
        with open(results_file, "w") as f:
            json.dump({
                "project_plan": {
                    "project_name": project_plan.project_name,
                    "description": project_plan.description,
                    "estimated_total_hours": project_plan.estimated_total_hours,
                    "tasks": [t.model_dump() for t in project_plan.tasks]
                },
                "execution_plan": execution_plan
            }, f, indent=2)
        print(f"\n📝 Results saved to: {results_file}")

    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    test_meta_agent()
