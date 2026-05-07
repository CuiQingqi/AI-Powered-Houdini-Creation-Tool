"""
Houdini Shelf Tool entry point for the AI Bridge.

Copy this code into a new Houdini Shelf Tool (Python script).
"""

import sys
import os

AGENT_PATH = r"E:\Design\Houdini_AI\selfHoudiniAgent"
if AGENT_PATH not in sys.path:
    sys.path.insert(0, AGENT_PATH)

LIB_PATH = os.path.join(AGENT_PATH, "lib")
if os.path.isdir(LIB_PATH) and LIB_PATH not in sys.path:
    sys.path.insert(0, LIB_PATH)

# Clear cached modules for fresh reload
for k in list(sys.modules.keys()):
    if k.startswith('bridge'):
        del sys.modules[k]

from bridge.server import get_bridge_server, start_bridge, stop_bridge
from bridge.task_queue import start_worker, stop_worker, is_worker_running

server = get_bridge_server()

if server.is_running:
    stop_bridge()
    stop_worker()
    print("Bridge stopped")
else:
    # Start the main-thread worker first
    start_worker(interval_ms=50)
    # Then start the WebSocket server on daemon thread
    start_bridge("127.0.0.1", 9877)
    print("Bridge started on ws://127.0.0.1:9877")
