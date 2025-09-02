from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request, BackgroundTasks
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.security.webhook_sign import verify_webhook_signature
from app.services.idempotency import try_lock, body_hash
from app.services.emitter import send_step
from app.services.workflow import start_workflow
from app.store.db import get_session
from app.store.models import Incident, Action

from app.observability import webhook_incoming_counter

router = APIRouter()


class AlertIn(BaseModel):
    source: str = Field(..., max_length=100)
    type: str = Field(..., alias="type")
    severity: str
    entity: str
    raw: dict

    class Config:
        populate_by_name = True




@router.post("/webhook/siem")
async def webhook_siem(
    request: Request,
    payload: AlertIn,
    background_tasks: BackgroundTasks,
    _=Depends(verify_webhook_signature),
    session: AsyncSession = Depends(get_session),
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
):
    # Increment custom metric for incoming webhook
    webhook_incoming_counter.labels(endpoint="/webhook/siem").inc()

    raw_body = await request.body()
    key = idempotency_key or body_hash(raw_body or b"null")
    if not try_lock(key, ttl=300):
        raise HTTPException(status_code=409, detail={"message": "Duplicate webhook", "key": key})

    incident = Incident(source=payload.source, status="received", summary=None)
    session.add(incident)
    await session.flush()  # to get incident.id

    action = Action(incident_id=incident.id, kind="received_alert", payload_json=payload.model_dump(by_alias=True))
    session.add(action)
    await session.commit()

    # Emit event to websocket listeners
    await send_step(incident.id, "received_alert", alert=payload.model_dump(by_alias=True))

    background_tasks.add_task(start_workflow, incident.id)

    return {"incident_id": incident.id}
