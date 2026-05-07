"""
WebSocket client for connecting to the Houdini Bridge.

Handles JSON-RPC request/response correlation, auto-reconnection,
and timeout management. Runs as part of the MCP Server process.
"""

import asyncio
import json
import logging
import time
import uuid
from typing import Any, Callable, Coroutine, Dict, Optional

logger = logging.getLogger("mcp_server.bridge_client")

try:
    import websockets
    from websockets.asyncio.client import connect as ws_connect
    HAS_WEBSOCKETS = True
except ImportError:
    HAS_WEBSOCKETS = False


class BridgeClient:
    """WebSocket client that communicates with the Houdini Bridge.

    Maintains a persistent connection with automatic reconnection and
    handles JSON-RPC request/response correlation using unique request IDs.
    """

    def __init__(self, url: str = "ws://127.0.0.1:9877"):
        """
        Args:
            url: WebSocket URL of the Houdini Bridge.
        """
        self._url: str = url
        self._ws: Optional[Any] = None
        self._connected: bool = False
        self._pending: Dict[str, asyncio.Future] = {}
        self._event_handlers: list[Callable] = []
        self._running: bool = False
        self._reconnect_delay: float = 1.0
        self._max_reconnect_delay: float = 60.0
        self._message_task: Optional[asyncio.Task] = None

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def url(self) -> str:
        return self._url

    async def connect(self) -> bool:
        """Establish connection to the Houdini Bridge. Auto-reconnects on failure."""
        if not HAS_WEBSOCKETS:
            logger.error("websockets package not installed")
            return False

        self._running = True
        return await self._connect_loop()

    async def disconnect(self) -> None:
        """Gracefully disconnect from the Houdini Bridge."""
        self._running = False
        if self._message_task:
            self._message_task.cancel()
            self._message_task = None
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None
        self._connected = False
        # Fail all pending requests
        for req_id, future in self._pending.items():
            if not future.done():
                future.set_exception(ConnectionError("Disconnected from Houdini Bridge"))
        self._pending.clear()

    def on_event(self, handler: Callable[[str, Dict[str, Any]], Coroutine]) -> None:
        """Register an async callback for push events from the Bridge.

        Args:
            handler: Async callable(event_method, event_params).
        """
        self._event_handlers.append(handler)

    async def call_tool(self, method: str, params: Dict[str, Any] = None,
                        timeout: float = 30.0) -> Dict[str, Any]:
        """Call a tool method on the Houdini Bridge and wait for the result.

        Args:
            method: JSON-RPC method name, e.g. "tool.create_node".
            params: Parameters dict for the method.
            timeout: Maximum wait time in seconds.

        Returns:
            Result dict from the bridge (the "result" field from JSON-RPC response).

        Raises:
            ConnectionError: If not connected to the bridge.
            TimeoutError: If the bridge doesn't respond in time.
            RuntimeError: If the bridge returns an error.
        """
        if not self._connected or self._ws is None:
            raise ConnectionError("Not connected to Houdini Bridge")

        req_id = str(uuid.uuid4())[:8]
        request = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params or {},
        }

        future: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[req_id] = future

        try:
            await self._ws.send(json.dumps(request, default=str))
            result = await asyncio.wait_for(future, timeout=timeout)
            return result
        except asyncio.TimeoutError:
            raise TimeoutError(f"Tool call '{method}' timed out after {timeout}s")
        finally:
            self._pending.pop(req_id, None)

    async def _connect_loop(self) -> bool:
        """Connect with exponential backoff retry."""
        self._reconnect_delay = 1.0
        while self._running:
            try:
                self._ws = await ws_connect(self._url, ping_interval=15)
                self._connected = True
                self._reconnect_delay = 1.0
                logger.info(f"Connected to Houdini Bridge at {self._url}")

                # Start message listener
                self._message_task = asyncio.create_task(self._listen())
                return True
            except Exception as e:
                self._connected = False
                logger.warning(
                    f"Failed to connect to Houdini Bridge: {e}. "
                    f"Retrying in {self._reconnect_delay:.1f}s..."
                )
                await asyncio.sleep(self._reconnect_delay)
                self._reconnect_delay = min(
                    self._reconnect_delay * 2,
                    self._max_reconnect_delay,
                )
        return False

    async def _listen(self) -> None:
        """Listen for incoming messages from the Bridge."""
        try:
            async for raw_message in self._ws:
                try:
                    message = json.loads(raw_message)
                except json.JSONDecodeError:
                    logger.warning(f"Invalid JSON from bridge: {raw_message[:200]}")
                    continue

                msg_id = message.get("id")

                if msg_id is None:
                    # Push event — notify handlers
                    method = message.get("method", "")
                    params = message.get("params", {})
                    for handler in self._event_handlers:
                        try:
                            await handler(method, params)
                        except Exception as exc:
                            logger.error(f"Event handler error: {exc}")
                else:
                    # Response to a pending request
                    future = self._pending.get(msg_id)
                    if future and not future.done():
                        if "error" in message:
                            error = message["error"]
                            future.set_exception(
                                RuntimeError(f"Bridge error [{error.get('code')}]: {error.get('message')}")
                            )
                        else:
                            future.set_result(message.get("result", {}))
        except websockets.exceptions.ConnectionClosed:
            logger.warning("Bridge connection closed")
        except Exception as e:
            logger.error(f"Bridge listener error: {e}")
        finally:
            self._connected = False
            # Trigger reconnection
            if self._running:
                asyncio.create_task(self._reconnect())

    async def _reconnect(self) -> None:
        """Reconnect after a disconnection."""
        self._connected = False
        await self._connect_loop()
