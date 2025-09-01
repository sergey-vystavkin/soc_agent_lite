from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Dict, Any
from abc import ABC, abstractmethod


@dataclass(frozen=True)
class Alert:
    source: str
    type: str
    severity: str
    entity: str
    raw: Dict[str, Any]


@dataclass(frozen=True)
class Step:
    kind: str
    params: Dict[str, Any] | None = None


@dataclass(frozen=True)
class Findings:
    items: List[Dict[str, Any]]
    summary: Optional[str] = None


class LLMClient(ABC):
    """Interface for LLM adapter used by the agent service.

    - plan_investigation: given an alert, produce a list of high-level steps
      that the service (executor) will run.
    - summarize: given investigation findings (arbitrary dicts), return a
      concise summary string.
    """

    @abstractmethod
    def plan_investigation(self, alert: Alert) -> List[Step]:
        raise NotImplementedError

    @abstractmethod
    def summarize(self, findings: Findings) -> str:
        raise NotImplementedError


class RuleBasedLLMClient(LLMClient):
    """Simple rules-only LLM client placeholder.

    This will be replaced later by a real LLM (OpenAI/Claude). For now,
    implements deterministic planning so that different alerts yield
    different plans.
    """

    def plan_investigation(self, alert: Alert) -> List[Step]:
        t = (alert.type or "").lower()

        if t == "login_anomaly":
            ip = alert.raw.get("ip") if isinstance(alert.raw, dict) else None
            user = alert.raw.get("user") if isinstance(alert.raw, dict) else None
            url = alert.raw.get("url") if isinstance(alert.raw, dict) else None
            steps: List[Step] = [
                Step("run_query", {"by": "ip", "ip": ip} if ip else {"by": "ip"}),
                Step("run_query", {"by": "user", "user": user} if user else {"by": "user"}),
                Step("capture_evidence", {"url": url} if url else {"url": None}),
                Step("create_ticket", {"severity": alert.severity, "entity": alert.entity}),
            ]
            return steps

        if t == "malware_detection":
            return [
                Step("isolate_host", {"entity": alert.entity}),
                Step("run_query", {"by": "hash", "hash": alert.raw.get("hash") if isinstance(alert.raw, dict) else None}),
                Step("capture_evidence", {"artifact": "malware_sample"}),
                Step("create_ticket", {"severity": alert.severity, "entity": alert.entity}),
            ]

        if t == "data_exfiltration":
            return [
                Step("run_query", {"by": "user", "user": alert.entity}),
                Step("run_query", {"by": "ip", "ip": alert.raw.get("ip") if isinstance(alert.raw, dict) else None}),
                Step("increase_monitoring", {"entity": alert.entity}),
                Step("create_ticket", {"severity": alert.severity, "entity": alert.entity}),
            ]

        return [
            Step("triage", {"type": alert.type, "entity": alert.entity, "severity": alert.severity}),
            Step("create_ticket", {"severity": alert.severity, "entity": alert.entity}),
        ]

    def summarize(self, findings: Findings) -> str:
        if not findings.items:
            return "No findings available."
        parts: List[str] = []
        for i, item in enumerate(findings.items, start=1):
            desc = ", ".join(f"{k}={v}" for k, v in list(item.items())[:6])
            parts.append(f"[{i}] {desc}")
        base = "; ".join(parts)
        if findings.summary:
            return f"Summary: {findings.summary}. Details: {base}"
        return base


_default_client: LLMClient = RuleBasedLLMClient()


def get_llm_client() -> LLMClient:
    return _default_client
