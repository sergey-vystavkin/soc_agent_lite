from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import select

from app.store.db import SessionLocal
from app.store.models import Incident, Ticket


async def create_ticket(incident: Incident | int, findings: Optional[List[Dict[str, Any]]] = None, evidence: Optional[List[Dict[str, Any]]] = None) -> Ticket:
    """
    Emulate creating a ticket in an external system (Jira/ServiceNow).

    Behavior:
    - Write a Ticket row linked to the incident.
    - Use system="demo" and external_id=f"TCK-{inc_id}".
    - Status is set to "open".
    - Return the persisted Ticket ORM object.
    """
    # Normalize incident id
    if isinstance(incident, int):
        incident_id = incident
    else:
        incident_id = incident.id

    async with SessionLocal() as session:
        # Ensure incident exists if provided as id
        res = await session.execute(select(Incident).where(Incident.id == incident_id))
        inc = res.scalar_one_or_none()
        if not inc:
            raise ValueError("Incident not found")

        t = Ticket(
            incident_id=incident_id,
            external_id=f"TCK-{incident_id}",
            system="demo",
            status="open",
        )
        session.add(t)
        await session.flush()
        await session.refresh(t)
        await session.commit()
        return t
