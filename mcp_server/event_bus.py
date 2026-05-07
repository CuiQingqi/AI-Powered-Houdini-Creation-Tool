"""
Simple async pub/sub event bus.

Routes events from MCP tool dispatch to WebSocket-connected browsers
for the auxiliary Web UI. Topics map to Web UI event types.
"""

import asyncio
import logging
from typing import Any, Callable, Coroutine, Dict, List

logger = logging.getLogger("mcp_server.event_bus")

# Callback signature: async def callback(event_type: str, data: dict) -> None
EventHandler = Callable[[str, Dict[str, Any]], Coroutine[Any, Any, None]]


class EventBus:
    """Async pub/sub for MCP → Web UI events."""

    def __init__(self):
        self._subscribers: Dict[str, List[EventHandler]] = {}
        self._global_handlers: List[EventHandler] = []

    def subscribe(self, topic: str, handler: EventHandler) -> None:
        """Subscribe to a specific topic."""
        if topic not in self._subscribers:
            self._subscribers[topic] = []
        self._subscribers[topic].append(handler)

    def unsubscribe(self, topic: str, handler: EventHandler) -> None:
        """Remove a subscription."""
        if topic in self._subscribers:
            self._subscribers[topic] = [
                h for h in self._subscribers[topic] if h is not handler
            ]

    def on_event(self, handler: EventHandler) -> None:
        """Subscribe to all events (global handler)."""
        self._global_handlers.append(handler)

    async def publish(self, topic: str, data: Dict[str, Any]) -> None:
        """Publish an event to all subscribers of the topic and global handlers."""
        tasks = []

        # Topic-specific handlers
        for handler in self._subscribers.get(topic, []):
            tasks.append(self._safe_invoke(handler, topic, data))

        # Global handlers
        for handler in self._global_handlers:
            tasks.append(self._safe_invoke(handler, topic, data))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _safe_invoke(self, handler: EventHandler, topic: str, data: dict) -> None:
        """Invoke a handler, logging but not raising exceptions."""
        try:
            await handler(topic, data)
        except Exception as e:
            logger.error(f"Event handler error for '{topic}': {e}")
