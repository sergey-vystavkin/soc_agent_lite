from __future__ import annotations

from typing import Optional, Literal, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field


class HealthOut(BaseModel):
    status: Literal["ok"] = Field(description="Service status")


class WebhookResponse(BaseModel):
    incident_id: int = Field(..., description="Created incident identifier")


class Pagination(BaseModel):
    limit: int
    offset: int
    total: int
    returned: int


class ActionOut(BaseModel):
    id: int
    kind: str
    payload: Dict[str, Any] | None = Field(default=None, description="Action payload, if any")
    at: Optional[datetime] = Field(default=None, description="Action timestamp")


class EvidenceOut(BaseModel):
    id: int
    kind: str
    path: str
    hash: str
    at: Optional[datetime] = None


class TicketOut(BaseModel):
    external_id: Optional[str] = None
    system: Optional[str] = None
    status: Optional[str] = None
    at: Optional[datetime] = None


class IncidentOut(BaseModel):
    id: int
    source: Optional[str] = None
    status: Optional[str] = None
    summary: Optional[str] = None
    created_at: Optional[datetime] = None
    ticket: Optional[TicketOut] = None
    actions: List[ActionOut] = []
    actions_pagination: Pagination
    evidence: List[EvidenceOut] = []
