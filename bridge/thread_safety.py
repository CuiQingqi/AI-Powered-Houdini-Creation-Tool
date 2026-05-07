"""
Thread-safe dispatch to Houdini's main thread.

Uses a queue-based approach: daemon thread pushes tasks,
the main-thread QTimer worker processes them.
No Qt or hou access from non-main threads.
"""

import threading
from typing import Any, Callable


class HoudiniThreadError(Exception):
    """Raised when an operation on Houdini's main thread fails."""


def run_on_main_thread(fn: Callable[..., Any], *args: Any,
                       timeout: float = 15.0, **kwargs: Any) -> Any:
    """Execute fn on Houdini's main thread, block until done.

    Uses the task queue — daemon thread submits, main thread executes.
    """
    from .task_queue import submit
    return submit(fn, *args, timeout=timeout, **kwargs)


def is_houdini_available() -> bool:
    """Check if we're running inside Houdini."""
    try:
        import hou
        return hou is not None
    except Exception:
        return False


def run_on_main_thread_async(fn: Callable[..., Any], *args: Any,
                              **kwargs: Any) -> None:
    """Fire-and-forget: schedule fn on main thread, don't wait."""
    import threading
    t = threading.Thread(target=lambda: run_on_main_thread(fn, *args, **kwargs),
                         daemon=True)
    t.start()
