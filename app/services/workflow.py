from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from sqlalchemy import select

from app.services.emitter import send_step
from app.services.llm_client import get_llm_client, Alert, Findings, Step
from app.services import log_query
from app.store.db import SessionLocal
from app.store.models import Incident, Action, Ticket, Evidence
from datetime import datetime
import os
import hashlib
from playwright.async_api import async_playwright
from app.services.ticketing import create_ticket as create_demo_ticket
from time import perf_counter
from app.observability import workflow_duration_seconds


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






async def capture_evidence(incident_id: int, url: Optional[str]) -> List[Dict[str, Any]]:
    """Capture webpage evidence using Playwright.

    - Launch headless Chromium.
    - goto(url) if provided; otherwise a blank page.
    - Save screenshot to evidence/INC-{incident_id}-{ts}.png.
    - Compute sha256 and write a DB Evidence record.
    - Save PDF and tracing/HAR alongside screenshot.

    Returns a dict with file paths and hash for telemetry.
    """
    # Prepare dirs and filenames
    
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%S%fZ")
    base_dir = os.path.join(os.getcwd(), "evidence")
    os.makedirs(base_dir, exist_ok=True)
    base_name = f"INC-{incident_id}-{ts}"

    screenshot_path = os.path.join(base_dir, f"{base_name}.png")
    pdf_path = os.path.join(base_dir, f"{base_name}.pdf")
    trace_zip = os.path.join(base_dir, f"{base_name}-trace.zip")
    har_path = os.path.join(base_dir, f"{base_name}.har")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(record_har_path=har_path)
        await context.tracing.start(screenshots=True, snapshots=True, sources=True)
        page = await context.new_page()
        target = url or "about:blank"
        await page.goto(target, wait_until="networkidle")
        await page.screenshot(path=screenshot_path, full_page=True)
        try:
            await page.pdf(path=pdf_path)
        except Exception:
            # PDF may fail on non-Chromium implementations or about:blank; ignore
            pdf_path = None
        await context.tracing.stop(path=trace_zip)
        await context.close()
        await browser.close()

    # Compute SHA256 for screenshot
    sha256_hex = None
    try:
        h = hashlib.sha256()
        with open(screenshot_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        sha256_hex = h.hexdigest()
    except Exception:
        sha256_hex = None

    # Persist Evidence record for screenshot (primary artifact)
    async with SessionLocal() as session:
        ev = Evidence(incident_id=incident_id, kind="screenshot", path=screenshot_path, hash=sha256_hex)
        session.add(ev)
        await session.flush()
        await session.commit()

    result_dict: Dict[str, Any] = {
        "screenshot": screenshot_path,
        "pdf": pdf_path,
        "trace": trace_zip,
        "har": har_path,
        "sha256": sha256_hex,
        "url": url,
    }

    return [result_dict]


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
    start_ts = perf_counter()
    try:
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
                        # Execute Playwright to capture evidence from URL (if provided)
                        url = (params or {}).get("url")
                        try:
                            result = await capture_evidence(incident_id, url)
                            findings.extend(result)
                            payload = {"step": {"kind": kind, "params": params}, "status": "ok", "results": result, "result_count": len(result)}
                        except Exception as ce:
                            payload = {"step": {"kind": kind, "params": params}, "status": "error", "error": str(ce)}
                        await _add_action(incident_id, "capture_evidence", payload)
                        await send_step(incident_id, "capture_evidence", **payload)

                    elif kind == "create_ticket":
                        # Create ticket in demo system and persist
                        t = await create_demo_ticket(incident_id, findings=findings, evidence=None)
                        saved = {"external_id": t.external_id, "system": t.system, "status": t.status}
                        # Log action for traceability
                        await _add_action(incident_id, "create_ticket", {"ticket": saved})
                        # add to findings as a dict with type metadata
                        findings.append({"type": "ticket", **saved})
                        await send_step(incident_id, "create_ticket", ticket=saved)

                    else:
                        payload = {"step": {"kind": kind, "params": params}, "status": "skipped_unknown"}
                        # record unknown step occurrence into findings for completeness
                        findings.append({"type": "unknown_step", "kind": kind, "params": params, "status": "skipped_unknown"})
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
    finally:
        # Observe workflow duration regardless of outcome
        try:
            duration = perf_counter() - start_ts
            workflow_duration_seconds.observe(duration)
        except Exception:
            pass
