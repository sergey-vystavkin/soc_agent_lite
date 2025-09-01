from __future__ import annotations

import asyncio
from typing import Any, Dict, List

from sqlalchemy import select

from app.services.emitter import send_step
from app.services.llm_client import get_llm_client, Alert, Findings, Step
from app.services import log_query
from app.store.db import SessionLocal
from app.store.models import Incident, Action, Ticket


async def _get_received_alert_payload(incident_id: int) -> Dict[str, Any]:
    async with SessionLocal() as session:
        # Ensure incident exists
        res_inc = await session.execute(select(Incident).where(Incident.id == incident_id))
        inc = res_inc.scalar_one_or_none()
        if not inc:
            raise ValueError("Incident not found")
        # Find first received_alert action
        res = await session.execute(
            select(Action)
            .where(Action.incident_id == incident_id, Action.kind == "received_alert")
            .order_by(Action.at.asc())
        )
        act: Action | None = res.scalars().first()
        if not act:
            raise ValueError("Initial alert action not found")
        return act.payload_json or {}


async def _add_action(incident_id: int, kind: str, payload: Dict[str, Any]) -> None:
    async with SessionLocal() as session:
        action = Action(incident_id=incident_id, kind=kind, payload_json=payload or {})
        session.add(action)
        await session.flush()
        await session.commit()


async def _mark_incident_status(incident_id: int, status: str) -> None:
    async with SessionLocal() as session:
        res = await session.execute(select(Incident).where(Incident.id == incident_id))
        inc = res.scalar_one_or_none()
        if not inc:
            return
        inc.status = status
        await session.commit()


async def _create_ticket_and_log(incident_id: int, ticket_data: Dict[str, Any]) -> Dict[str, Any]:
    async with SessionLocal() as session:
        t = Ticket(
            incident_id=incident_id,
            external_id=ticket_data["external_id"],
            system=ticket_data["system"],
            status=ticket_data["status"],
        )
        session.add(t)
        await session.flush()
        action = Action(incident_id=incident_id, kind="create_ticket", payload_json={"ticket": ticket_data})
        session.add(action)
        await session.flush()
        await session.commit()
        return ticket_data


async def start_workflow(incident_id: int) -> None:
    """Main orchestrator for incident workflow.

    Steps:
      1) send_step("llm_plan", ...), save step to Action
      2) execute steps one by one: run_query -> save result (as Action)
      3) capture_evidence -> execute Playwright (TBD; noop)
      4) create_ticket -> write as Ticket
      5) summarize -> update Incident.summary, status=resolved.
    On any error: send_step("failed", ...), mark incident status=failed.
    """
    await asyncio.sleep(20)

    async def fail(reason: str, details: Dict[str, Any] | None = None) -> None:
        # Update incident status and persist failure action
        await _mark_incident_status(incident_id, "failed")
        await _add_action(incident_id, "failed", {"reason": reason, **(details or {})})
        await send_step(incident_id, "failed", reason=reason, **(details or {}))

    try:
        # 0. Load incident and alert payload
        alert_payload = await _get_received_alert_payload(incident_id)

        # 1) LLM plan
        llm = get_llm_client()
        alert = Alert(
            source=alert_payload.get("source"),
            type=alert_payload.get("type"),
            severity=alert_payload.get("severity"),
            entity=alert_payload.get("entity"),
            raw=alert_payload.get("raw", {}),
        )
        steps: List[Step] = llm.plan_investigation(alert)
        plan_payload = {"steps": [{"kind": s.kind, "params": s.params} for s in steps]}

        # Save plan action and mark incident planning_done
        async with SessionLocal() as session:
            res = await session.execute(select(Incident).where(Incident.id == incident_id))
            inc = res.scalar_one_or_none()
            if not inc:
                raise ValueError("Incident not found")
            session.add(Action(incident_id=incident_id, kind="llm_plan", payload_json=plan_payload))
            inc.status = "planning_done"
            await session.flush()
            await session.commit()
        await send_step(incident_id, "llm_plan", **plan_payload)

        findings: List[Dict[str, Any]] = []

        # 2) Execute steps sequentially
        for step in steps:
            kind = step.kind
            params = step.params or {}
            try:
                if kind == "run_query":
                    by = params.get("by")
                    result: List[Dict[str, Any]] = []
                    if by == "ip" and params.get("ip"):
                        result = log_query.by_ip(str(params["ip"]))
                    elif by == "user" and params.get("user"):
                        result = log_query.by_user(str(params["user"]))
                    else:
                        result = []

                    findings.extend(result)
                    payload = {"step": {"kind": kind, "params": params}, "result_count": len(result)}
                    await _add_action(incident_id, "run_query", payload)
                    await send_step(incident_id, "run_query", **payload)

                elif kind == "capture_evidence":
                    payload = {"step": {"kind": kind, "params": params}, "status": "noop"}
                    await _add_action(incident_id, "capture_evidence", payload)
                    await send_step(incident_id, "capture_evidence", **payload)

                elif kind == "create_ticket":
                    ticket_data = {
                        "external_id": f"TCK-{incident_id}-{int(asyncio.get_event_loop().time()*1000)}",
                        "system": "local",
                        "status": "open",
                    }
                    saved = await _create_ticket_and_log(incident_id, ticket_data)
                    await send_step(incident_id, "create_ticket", ticket=saved)

                else:
                    payload = {"step": {"kind": kind, "params": params}, "status": "skipped_unknown"}
                    await _add_action(incident_id, kind, payload)
                    await send_step(incident_id, kind, **payload)

            except Exception as e:
                await fail(f"step_error:{kind}", {"error": str(e), "params": params})
                return

        # 5) Summarize and resolve
        try:
            summary_text = get_llm_client().summarize(Findings(items=findings))
            async with SessionLocal() as session:
                res = await session.execute(select(Incident).where(Incident.id == incident_id))
                inc = res.scalar_one_or_none()
                if not inc:
                    raise ValueError("Incident not found")
                inc.summary = summary_text
                inc.status = "resolved"
                session.add(Action(incident_id=incident_id, kind="summarize", payload_json={"summary": summary_text, "count": len(findings)}))
                await session.flush()
                await session.commit()
            await send_step(incident_id, "summarize", summary=summary_text)
            await send_step(incident_id, "done")
        except Exception as e:
            await fail("summarize_error", {"error": str(e)})
            return

    except Exception as e:
        await fail("workflow_error", {"error": str(e)})
        return
