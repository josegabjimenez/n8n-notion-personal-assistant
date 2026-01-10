import threading
import time
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from enum import Enum


class TaskStatus(Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    CONSUMED = "consumed"
    FAILED = "failed"


@dataclass
class BackgroundTask:
    id: str
    query: str
    status: TaskStatus
    result: Optional[str] = None
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None


class TaskStore:
    """Thread-safe in-memory store for background task results."""

    def __init__(self, max_tasks: int = 50, ttl_seconds: int = 300):
        self._tasks: Dict[str, BackgroundTask] = {}
        self._lock = threading.Lock()
        self._max_tasks = max_tasks
        self._ttl = ttl_seconds
        self._counter = 0

    def create_task(self, query: str) -> str:
        """Create a new pending task and return its ID."""
        with self._lock:
            self._cleanup_old_tasks()
            self._counter += 1
            task_id = f"task_{self._counter}"
            self._tasks[task_id] = BackgroundTask(
                id=task_id,
                query=query,
                status=TaskStatus.PENDING
            )
            return task_id

    def update_task(self, task_id: str, status: TaskStatus,
                    result: str = None, error: str = None):
        """Update task status and result."""
        with self._lock:
            if task_id in self._tasks:
                task = self._tasks[task_id]
                task.status = status
                if result is not None:
                    task.result = result
                if error is not None:
                    task.error = error
                if status in (TaskStatus.COMPLETED, TaskStatus.FAILED):
                    task.completed_at = time.time()

    def mark_consumed(self, task_id: str):
        """Mark a task as consumed (won't appear in future status queries)."""
        with self._lock:
            if task_id in self._tasks:
                self._tasks[task_id].status = TaskStatus.CONSUMED

    def get_pending_tasks(self) -> List[BackgroundTask]:
        """Get all tasks that are still processing."""
        with self._lock:
            return [
                t for t in self._tasks.values()
                if t.status in (TaskStatus.PENDING, TaskStatus.PROCESSING)
            ]

    def get_recent_completed(self) -> List[BackgroundTask]:
        """Get recently completed tasks (not consumed) for smart matching."""
        with self._lock:
            completed = [
                t for t in self._tasks.values()
                if t.status == TaskStatus.COMPLETED
            ]
            # Sort by completion time, most recent first
            return sorted(completed, key=lambda t: t.completed_at or 0, reverse=True)

    def get_task(self, task_id: str) -> Optional[BackgroundTask]:
        """Get a specific task by ID."""
        with self._lock:
            return self._tasks.get(task_id)

    def _cleanup_old_tasks(self):
        """Remove expired and consumed tasks."""
        now = time.time()

        # Remove expired tasks
        expired = [
            k for k, v in self._tasks.items()
            if now - v.created_at > self._ttl
        ]
        for k in expired:
            del self._tasks[k]

        # Remove consumed tasks
        consumed = [
            k for k, v in self._tasks.items()
            if v.status == TaskStatus.CONSUMED
        ]
        for k in consumed:
            del self._tasks[k]

        # Keep only max_tasks most recent
        if len(self._tasks) > self._max_tasks:
            sorted_tasks = sorted(
                self._tasks.items(),
                key=lambda x: x[1].created_at
            )
            for k, _ in sorted_tasks[:len(self._tasks) - self._max_tasks]:
                del self._tasks[k]
