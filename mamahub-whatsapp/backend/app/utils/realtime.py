"""In-memory WebSocket fan-out for inbox updates."""
from __future__ import annotations

import json
from typing import Any, Dict, List, Set

from fastapi import WebSocket

from app.core.logging import logger


class ConnectionManager:
    def __init__(self) -> None:
        self.connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.connections.add(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        self.connections.discard(websocket)

    async def broadcast(self, event: str, payload: Dict[str, Any]) -> None:
        message = json.dumps({"event": event, "payload": payload}, default=str)
        stale: List[WebSocket] = []
        for connection in list(self.connections):
            try:
                await connection.send_text(message)
            except Exception:  # noqa: BLE001
                stale.append(connection)
        for connection in stale:
            self.disconnect(connection)
        if stale:
            logger.debug("Dropped %s stale websocket connections", len(stale))


manager = ConnectionManager()
