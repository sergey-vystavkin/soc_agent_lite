from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.store.db import get_session
from app.store.models import Incident, Ticket

router = APIRouter()


@router.get("/incidents/{incident_id}")
async def get_incident(incident_id: int, session: AsyncSession = Depends(get_session)) -> dict:
    res = await session.execute(select(Incident).where(Incident.id == incident_id))
    inc: Optional[Incident] = res.scalar_one_or_none()
    if not inc:
        raise HTTPException(status_code=404, detail="Incident not found")

    # Load latest ticket if any
    res_t = await session.execute(
        select(Ticket).where(Ticket.incident_id == incident_id).order_by(Ticket.at.desc())
    )
    ticket: Optional[Ticket] = res_t.scalars().first()

    return {
        "id": inc.id,
        "source": inc.source,
        "status": inc.status,
        "summary": inc.summary,
        "created_at": inc.created_at.isoformat() if inc.created_at else None,
        "ticket": {
            "external_id": ticket.external_id,
            "system": ticket.system,
            "status": ticket.status,
            "at": ticket.at.isoformat() if ticket and ticket.at else None,
        } if ticket else None,
    }
