from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.store.db import get_session
from app.store.models import Incident, Ticket, Action, Evidence

router = APIRouter()


@router.get("/incidents/{incident_id}")
async def get_incident(
    incident_id: int,
    session: AsyncSession = Depends(get_session),
    limit: int = Query(20, ge=0, le=200, description="Max number of actions to return"),
    offset: int = Query(0, ge=0, description="Number of actions to skip"),
) -> dict:
    res = await session.execute(select(Incident).where(Incident.id == incident_id))
    inc: Optional[Incident] = res.scalar_one_or_none()
    if not inc:
        raise HTTPException(status_code=404, detail="Incident not found")

    res_t = await session.execute(
        select(Ticket).where(Ticket.incident_id == incident_id).order_by(Ticket.at.desc())
    )
    ticket: Optional[Ticket] = res_t.scalars().first()

    # Actions with pagination and total count
    total_res = await session.execute(
        select(func.count()).select_from(Action).where(Action.incident_id == incident_id)
    )
    total_actions: int = total_res.scalar_one()

    actions_res = await session.execute(
        select(Action)
        .where(Action.incident_id == incident_id)
        .order_by(Action.at.desc())
        .offset(offset)
        .limit(limit)
    )
    actions = [
        {
            "id": a.id,
            "kind": a.kind,
            "payload": a.payload_json,
            "at": a.at.isoformat() if a.at else None,
        }
        for a in actions_res.scalars().all()
    ]

    # Evidence list (non-paginated, typically small per incident)
    ev_res = await session.execute(
        select(Evidence).where(Evidence.incident_id == incident_id).order_by(Evidence.at.desc())
    )
    evidence = [
        {
            "id": e.id,
            "kind": e.kind,
            "path": e.path,
            "hash": e.hash,
            "at": e.at.isoformat() if e.at else None,
        }
        for e in ev_res.scalars().all()
    ]

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
        "actions": actions,
        "actions_pagination": {
            "limit": limit,
            "offset": offset,
            "total": total_actions,
            "returned": len(actions),
        },
        "evidence": evidence,
    }
