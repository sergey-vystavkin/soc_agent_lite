from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.emitter import manager

router = APIRouter()


@router.websocket("/ws/incidents/{incident_id}")
async def ws_incident(websocket: WebSocket, incident_id: str):
    await websocket.accept(subprotocol=None)
    await manager.connect(incident_id, websocket)
    try:
        await websocket.send_json({"event": "connected", "incident_id": str(incident_id)})
        while True:
            try:
                _ = await websocket.receive_text()
                await websocket.send_json({"event": "pong"})
            except WebSocketDisconnect:
                break
    finally:
        await manager.disconnect(incident_id, websocket)
