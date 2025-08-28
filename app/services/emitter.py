from __future__ import annotations

import asyncio
from typing import Dict, Set, Any

from fastapi import WebSocket


class IncidentWSManager:
    """Simple per-incident WebSocket connection manager."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._connections: Dict[str, Set[WebSocket]] = {}

    async def connect(self, incident_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            conns = self._connections.setdefault(incident_id, set())
            conns.add(websocket)

    async def disconnect(self, incident_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            conns = self._connections.get(incident_id)
            if not conns:
                return
            conns.discard(websocket)
            if not conns:
                self._connections.pop(incident_id, None)

    async def send_json(self, incident_id: str, message: Any) -> None:
        # Send to all connections for the incident; drop dead ones silently
        conns = list(self._connections.get(incident_id, set()))
        to_remove: list[WebSocket] = []
        for ws in conns:
            try:
                await ws.send_json(message)
            except Exception:
                to_remove.append(ws)
        if to_remove:
            async with self._lock:
                conns2 = self._connections.get(incident_id)
                if conns2:
                    for ws in to_remove:
                        conns2.discard(ws)
                    if not conns2:
                        self._connections.pop(incident_id, None)


manager = IncidentWSManager()


async def send_step(incident_id: int | str, event: str, **payload: Any) -> None:
    """Public helper used by workflow steps to emit progress events.

    Example: await send_step(42, "received_alert", details={...})
    """
    message = {"event": event, "incident_id": str(incident_id)}
    if payload:
        message.update(payload)
    await manager.send_json(str(incident_id), message)
