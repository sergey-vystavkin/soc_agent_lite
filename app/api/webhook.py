from __future__ import annotations

from typing import Optional
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Request, BackgroundTasks
from pydantic import BaseModel, Field
from sqlalchemy import exc as sa_exc
from app.api.schemas import WebhookResponse
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




@router.post("/webhook/siem", response_model=WebhookResponse)
async def webhook_siem(
    request: Request,
    payload: AlertIn,
    background_tasks: BackgroundTasks,
    _=Depends(verify_webhook_signature),
    session: AsyncSession = Depends(get_session),
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    tenant_id: str = Header(alias="X-Tenant"),
):
    # Increment custom metric for incoming webhook
    webhook_incoming_counter.labels(endpoint="/webhook/siem").inc()

    raw_body = await request.body()
    key = idempotency_key or body_hash(raw_body or b"null")
    if not try_lock(key, ttl=300):
        raise HTTPException(status_code=409, detail={"message": "Duplicate webhook", "key": key})

    # Validate tenant as UUID format
    try:
        parsed = uuid.UUID(tenant_id)
        tenant_id = str(parsed)
    except Exception:
        raise HTTPException(status_code=400, detail={"message": "Invalid X-Tenant header; expected UUID"})

    try:
        incident = Incident(source=payload.source, status="received", summary=None, tenant_id=tenant_id)
        session.add(incident)
        await session.flush()  # to get incident.id

        action = Action(incident_id=incident.id, kind="received_alert", payload_json=payload.model_dump(by_alias=True))
        session.add(action)
        await session.commit()
    except sa_exc.IntegrityError as e:
        await session.rollback()
        # Return 400 instead of 500 for any DB constraint violation (test DB is permissive)
        raise HTTPException(status_code=400, detail={"message": "Invalid data rejected by database constraint", "error": str(e)})

    # Emit event to websocket listeners
    await send_step(incident.id, "received_alert", alert=payload.model_dump(by_alias=True))

    background_tasks.add_task(start_workflow, incident.id)

    return WebhookResponse(incident_id=incident.id)
