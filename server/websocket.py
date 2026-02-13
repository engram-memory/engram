"""WebSocket hub for real-time memory events."""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import WebSocket

log = logging.getLogger(__name__)


class ConnectionManager:
    """Manages per-namespace WebSocket connections."""

    def __init__(self) -> None:
        self._connections: dict[str, list[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, namespace: str) -> None:
        await websocket.accept()
        self._connections.setdefault(namespace, []).append(websocket)

    def disconnect(self, websocket: WebSocket, namespace: str) -> None:
        conns = self._connections.get(namespace, [])
        if websocket in conns:
            conns.remove(websocket)

    async def broadcast(self, namespace: str, event: str, data: dict[str, Any]) -> None:
        """Send *event* to all clients listening on *namespace*."""
        message = json.dumps({"event": event, **data})
        for ws in list(self._connections.get(namespace, [])):
            try:
                await ws.send_text(message)
            except Exception:
                log.debug("WebSocket disconnected from namespace %s", namespace)
                self.disconnect(ws, namespace)


manager = ConnectionManager()
