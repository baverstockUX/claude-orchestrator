"""Dependency graph (DAG) for task management."""

import logging
from typing import Optional

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class TaskNode(BaseModel):
    """Node in the task dependency graph."""
    task_id: str
    title: str
    agent_type: str
    dependencies: list[str] = []
    estimated_hours: float = 2.0


class DependencyGraph:
    """Directed Acyclic Graph (DAG) for task dependencies."""

    def __init__(self):
        """Initialize empty graph."""
        self.nodes: dict[str, TaskNode] = {}
        self.edges: dict[str, list[str]] = {}  # task_id -> list of dependent task_ids

    def add_node(self, node: TaskNode) -> None:
        """
        Add task node to graph.

        Args:
            node: Task node to add
        """
        if node.task_id in self.nodes:
            logger.warning(f"Task {node.task_id} already exists in graph, replacing")

        self.nodes[node.task_id] = node

        # Initialize edges
        if node.task_id not in self.edges:
            self.edges[node.task_id] = []

        # Add edges for dependencies
        for dep_id in node.dependencies:
            if dep_id not in self.edges:
                self.edges[dep_id] = []
            self.edges[dep_id].append(node.task_id)

    def get_ready_tasks(self) -> list[TaskNode]:
        """
        Get all tasks that have no unsatisfied dependencies.

        Returns:
            List of tasks ready to execute
        """
        ready = []

        for task_id, node in self.nodes.items():
            # Task is ready if it has no dependencies
            if not node.dependencies:
                ready.append(node)

        return ready

    def get_dependent_tasks(self, task_id: str) -> list[TaskNode]:
        """
        Get all tasks that depend on the given task.

        Args:
            task_id: Task ID to check

        Returns:
            List of dependent tasks
        """
        dependent_ids = self.edges.get(task_id, [])
        return [self.nodes[dep_id] for dep_id in dependent_ids if dep_id in self.nodes]

    def mark_completed(self, task_id: str) -> list[TaskNode]:
        """
        Mark task as completed and return newly ready tasks.

        Args:
            task_id: Task ID that completed

        Returns:
            List of tasks that are now ready (all dependencies satisfied)
        """
        if task_id not in self.nodes:
            logger.warning(f"Task {task_id} not found in graph")
            return []

        newly_ready = []

        # Check all tasks that depend on this one
        for dependent_id in self.edges.get(task_id, []):
            if dependent_id not in self.nodes:
                continue

            dependent_node = self.nodes[dependent_id]

            # Remove this dependency
            if task_id in dependent_node.dependencies:
                dependent_node.dependencies.remove(task_id)

            # Check if all dependencies are now satisfied
            if not dependent_node.dependencies:
                newly_ready.append(dependent_node)

        return newly_ready

    def validate_acyclic(self) -> tuple[bool, Optional[list[str]]]:
        """
        Validate that graph is acyclic (no circular dependencies).

        Returns:
            Tuple of (is_valid, cycle_path if invalid)
        """
        visited = set()
        rec_stack = set()

        def has_cycle(task_id: str, path: list[str]) -> Optional[list[str]]:
            """DFS to detect cycles."""
            visited.add(task_id)
            rec_stack.add(task_id)
            path.append(task_id)

            # Check all dependent tasks
            for dependent_id in self.edges.get(task_id, []):
                if dependent_id not in visited:
                    cycle = has_cycle(dependent_id, path.copy())
                    if cycle:
                        return cycle
                elif dependent_id in rec_stack:
                    # Found cycle
                    return path + [dependent_id]

            rec_stack.remove(task_id)
            return None

        # Check each node
        for task_id in self.nodes:
            if task_id not in visited:
                cycle = has_cycle(task_id, [])
                if cycle:
                    return False, cycle

        return True, None

    def get_execution_order(self) -> list[list[str]]:
        """
        Get topological sort of tasks (execution order by levels).

        Returns:
            List of levels, where each level contains task IDs that can run in parallel

        Raises:
            ValueError: If graph has cycles
        """
        # Validate acyclic
        is_valid, cycle = self.validate_acyclic()
        if not is_valid:
            raise ValueError(f"Graph has circular dependency: {' -> '.join(cycle)}")

        # Calculate in-degree for each node
        in_degree = {task_id: len(node.dependencies) for task_id, node in self.nodes.items()}

        levels = []
        remaining = set(self.nodes.keys())

        while remaining:
            # Find all nodes with in-degree 0
            current_level = [
                task_id for task_id in remaining
                if in_degree[task_id] == 0
            ]

            if not current_level:
                # Should not happen if graph is acyclic
                raise ValueError("No tasks with in-degree 0, but graph not empty")

            levels.append(current_level)

            # Remove current level nodes and update in-degrees
            for task_id in current_level:
                remaining.remove(task_id)

                # Decrease in-degree of dependent tasks
                for dependent_id in self.edges.get(task_id, []):
                    if dependent_id in in_degree:
                        in_degree[dependent_id] -= 1

        return levels

    def get_critical_path(self) -> tuple[list[str], float]:
        """
        Calculate critical path (longest path through graph).

        Returns:
            Tuple of (task_ids in critical path, total estimated hours)
        """
        # Calculate earliest start time for each task
        earliest_start = {}
        task_order = []

        # Topological sort
        levels = self.get_execution_order()
        for level in levels:
            task_order.extend(level)

        # Calculate earliest start for each task
        for task_id in task_order:
            node = self.nodes[task_id]

            if not node.dependencies:
                earliest_start[task_id] = 0.0
            else:
                # Start after all dependencies complete
                max_finish = max(
                    earliest_start.get(dep_id, 0.0) + self.nodes[dep_id].estimated_hours
                    for dep_id in node.dependencies
                )
                earliest_start[task_id] = max_finish

        # Find task with latest finish time
        latest_finish_task = max(
            self.nodes.keys(),
            key=lambda tid: earliest_start[tid] + self.nodes[tid].estimated_hours
        )

        # Trace back critical path
        critical_path = []
        current = latest_finish_task
        total_hours = 0.0

        while current:
            critical_path.insert(0, current)
            total_hours += self.nodes[current].estimated_hours

            # Find predecessor on critical path
            predecessors = [
                dep_id for dep_id in self.nodes[current].dependencies
                if earliest_start[dep_id] + self.nodes[dep_id].estimated_hours == earliest_start[current]
            ]

            current = predecessors[0] if predecessors else None

        return critical_path, total_hours

    def get_total_estimated_hours(self) -> float:
        """
        Get sum of all task estimated hours.

        Returns:
            Total estimated hours (sequential execution time)
        """
        return sum(node.estimated_hours for node in self.nodes.values())

    def get_parallel_estimated_hours(self) -> float:
        """
        Get estimated time if tasks are executed in parallel.

        Returns:
            Parallel execution time (considering dependencies)
        """
        levels = self.get_execution_order()
        total_time = 0.0

        for level in levels:
            # Time for this level is the max of all parallel tasks
            level_time = max(
                self.nodes[task_id].estimated_hours
                for task_id in level
            )
            total_time += level_time

        return total_time
