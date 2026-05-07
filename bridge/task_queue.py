"""
Thread-safe task queue for executing hou operations on the main thread.

The daemon thread pushes tasks; the main thread (via QTimer) processes them.
No Qt or hou access from the daemon thread.

Usage (shelf tool):
    from bridge.task_queue import start_worker, stop_worker
    start_worker()   # starts QTimer polling on main thread
"""

import queue
import threading
import time
import traceback
from typing import Any, Callable, Dict, Optional

_pending = queue.Queue()
_results: Dict[str, dict] = {}
_results_lock = threading.Lock()
_worker_timer = None
_worker_running = False


def submit(fn: Callable[..., Any], *args, timeout: float = 15.0, **kwargs) -> Any:
    """Submit a task to run on the main thread, block until done.

    Called from the daemon thread. Does NOT access Qt or hou.
    """
    import uuid
    task_id = str(uuid.uuid4())[:8]

    result_container = {"value": None, "error": None}
    event = threading.Event()

    with _results_lock:
        _results[task_id] = {"container": result_container, "event": event}

    _pending.put((task_id, fn, args, kwargs))

    if not event.wait(timeout=timeout):
        with _results_lock:
            _results.pop(task_id, None)
        raise TimeoutError(f"Task {task_id} timed out after {timeout}s")

    with _results_lock:
        _results.pop(task_id, None)

    if result_container["error"]:
        raise result_container["error"]
    return result_container["value"]


def _process_pending():
    """Process all pending tasks. Called by QTimer on the MAIN THREAD."""
    global _worker_running
    if not _worker_running:
        return

    # Process all pending items without blocking
    while True:
        try:
            task_id, fn, args, kwargs = _pending.get_nowait()
        except queue.Empty:
            break

        try:
            value = fn(*args, **kwargs)
            with _results_lock:
                if task_id in _results:
                    _results[task_id]["container"]["value"] = value
        except Exception as e:
            tb = traceback.format_exc()
            wrapped = RuntimeError(f"Task error: {e}\n{tb}")
            with _results_lock:
                if task_id in _results:
                    _results[task_id]["container"]["error"] = wrapped
        finally:
            with _results_lock:
                if task_id in _results:
                    _results[task_id]["event"].set()


def start_worker(interval_ms: int = 50):
    """Start the main-thread task worker using QTimer.

    Call this from the shelf tool (on the main thread).
    """
    global _worker_timer, _worker_running

    if _worker_running:
        return

    # Try PySide2 then PySide6
    QTimer = None
    try:
        from PySide2.QtCore import QTimer as qt
        QTimer = qt
    except ImportError:
        pass
    if QTimer is None:
        try:
            from PySide6.QtCore import QTimer as qt
            QTimer = qt
        except ImportError:
            pass

    if QTimer is None:
        print("[Bridge] Cannot start worker: PySide2/PySide6 not found")
        return

    _worker_running = True
    _worker_timer = QTimer()
    _worker_timer.timeout.connect(_process_pending)
    _worker_timer.start(interval_ms)
    print(f"[Bridge] Worker started (polling every {interval_ms}ms)")


def stop_worker():
    """Stop the main-thread task worker."""
    global _worker_timer, _worker_running
    _worker_running = False
    if _worker_timer is not None:
        _worker_timer.stop()
        _worker_timer = None


def is_worker_running() -> bool:
    return _worker_running
