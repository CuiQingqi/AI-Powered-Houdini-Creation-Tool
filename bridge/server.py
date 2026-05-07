"""
Socket-based Bridge server for Houdini 21 compatibility.

Houdini 21's haio.py blocks asyncio on non-main threads. This module uses
pure socket + threading (no asyncio, no haio) via SimpleWSServer.
"""

import json
import logging
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger("houdini_bridge.server")


class BridgeServer:
    """Manages the Bridge lifecycle using a socket-based WebSocket server."""

    def __init__(self):
        self._server = None
        self._running = False
        self._event_callbacks: list[Callable] = []

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def client_count(self) -> int:
        if self._server:
            return self._server.client_count
        return 0

    def start(self, host: str = "127.0.0.1", port: int = 9877) -> None:
        if self._running:
            logger.warning("Bridge is already running")
            return

        from .ws_server import SimpleWSServer
        from .handler import BridgeHandler

        handler = BridgeHandler(on_event=self._on_bridge_event, hou_available=True)
        self._handler = handler

        self._server = SimpleWSServer(host, port)
        self._server.set_handler(lambda req: handler.handle_request(req))

        if not self._server.start():
            raise RuntimeError(f"Failed to bind to {host}:{port}")

        self._running = True
        logger.info(f"Houdini Bridge listening on ws://{host}:{port}")

    def stop(self) -> None:
        self._running = False
        if self._server:
            self._server.stop()
            self._server = None
        logger.info("Houdini Bridge stopped")

    def on_event(self, callback: Callable) -> None:
        self._event_callbacks.append(callback)

    def push_event(self, method: str, params: Dict[str, Any] = None) -> None:
        """Push event to all clients. For socket-based server, events go through handler."""
        pass  # Events are pushed via handler responses

    def _on_bridge_event(self, method: str, params: Dict[str, Any]) -> None:
        for cb in self._event_callbacks:
            try:
                cb(method, params)
            except Exception:
                pass


_bridge_server: Optional[BridgeServer] = None


def get_bridge_server() -> BridgeServer:
    global _bridge_server
    if _bridge_server is None:
        _bridge_server = BridgeServer()
    return _bridge_server


def start_bridge(host: str = "127.0.0.1", port: int = 9877) -> BridgeServer:
    server = get_bridge_server()
    if not server.is_running:
        server.start(host, port)
    return server


def stop_bridge() -> None:
    global _bridge_server
    if _bridge_server and _bridge_server.is_running:
        _bridge_server.stop()
    _bridge_server = None
