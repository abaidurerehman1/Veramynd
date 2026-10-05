"""SME review decisions: accept or reject alignment citations before they reach a client report."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth.db import Base, get_db, get_engine
from .auth.models import ReviewDecision, User
from .auth.routes import get_current_user

router = APIRouter(prefix="/api/review", tags=["review"])

_table_ready = False


def _ensure_table() -> None:
    """Create the table on first use, so a running server picks it up without a restart."""
    global _table_ready
    if not _table_ready:
        Base.metadata.create_all(bind=get_engine(), tables=[ReviewDecision.__table__])
        _table_ready = True


def _decision_dict(row: ReviewDecision) -> dict:
    return {
        "item_id": row.item_id,
        "decision": row.decision,
        "reviewer": row.reviewer_name,
        "decided_at": row.decided_at.isoformat() if row.decided_at else None,
        "note": row.note,
    }


@router.get("/decisions")
def list_decisions(project_id: str, db: Annotated[Session, Depends(get_db)]) -> dict:
    try:
        _ensure_table()
    except Exception as e:  # DB down: report no decisions rather than failing the page.
        return {"project_id": project_id, "decisions": {}, "available": False, "error": str(e)}
    rows = db.scalars(select(ReviewDecision).where(ReviewDecision.project_id == project_id)).all()
    return {
        "project_id": project_id,
        "decisions": {r.item_id: _decision_dict(r) for r in rows},
        "available": True,
    }


class DecisionIn(BaseModel):
    project_id: str = Field(..., min_length=1, max_length=120)
    item_id: str = Field(..., min_length=1, max_length=255)
    # "pending" clears an earlier decision (Undo).
    decision: Literal["accepted", "rejected", "pending"]
    note: str | None = Field(default=None, max_length=2000)


@router.put("/decisions")
def set_decision(
    body: DecisionIn,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    try:
        _ensure_table()
    except Exception as e:
        raise HTTPException(503, f"Review storage unavailable: {e}") from e
    row = db.scalars(
        select(ReviewDecision).where(
            ReviewDecision.project_id == body.project_id,
            ReviewDecision.item_id == body.item_id,
        )
    ).first()
    if body.decision == "pending":
        if row:
            db.delete(row)
            db.commit()
        return {"ok": True, "item_id": body.item_id, "decision": None}
    if row is None:
        row = ReviewDecision(project_id=body.project_id, item_id=body.item_id, decision=body.decision)
        db.add(row)
    row.decision = body.decision
    row.reviewer_id = user.id
    row.reviewer_name = user.name or user.email
    row.note = body.note
    row.decided_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return {"ok": True, "item_id": body.item_id, "decision": _decision_dict(row)}
