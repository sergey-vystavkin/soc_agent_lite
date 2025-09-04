from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, ForeignKey, String, Text, JSON, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class Incident(Base):
    __tablename__ = "incidents"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="new")
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    actions: Mapped[list["Action"]] = relationship(back_populates="incident", cascade="all, delete-orphan")
    evidence: Mapped[list["Evidence"]] = relationship(back_populates="incident", cascade="all, delete-orphan")
    tickets: Mapped[list["Ticket"]] = relationship(back_populates="incident", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_incidents_created_at", "created_at"),
        Index("ix_incidents_status", "status"),
        Index("ix_incidents_tenant_id", "tenant_id"),
    )


class Action(Base):
    __tablename__ = "actions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(50), nullable=False)
    payload_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    at: Mapped[datetime] = mapped_column(default=datetime.utcnow, nullable=False)

    incident: Mapped[Incident] = relationship(back_populates="actions")

    __table_args__ = (
        Index("ix_actions_kind", "kind"),
        Index("ix_actions_at", "at"),
    )


class Evidence(Base):
    __tablename__ = "evidence"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(50), nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    hash: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    at: Mapped[datetime] = mapped_column(default=datetime.utcnow, nullable=False)

    incident: Mapped[Incident] = relationship(back_populates="evidence")

    __table_args__ = (
        Index("ix_evidence_kind", "kind"),
        Index("ix_evidence_at", "at"),
    )


class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False, index=True)
    external_id: Mapped[str] = mapped_column(String(100), nullable=False)
    system: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    at: Mapped[datetime] = mapped_column(default=datetime.utcnow, nullable=False)

    incident: Mapped[Incident] = relationship(back_populates="tickets")

    __table_args__ = (
        Index("ix_tickets_system", "system"),
        Index("ix_tickets_status", "status"),
        Index("ix_tickets_at", "at"),
    )
