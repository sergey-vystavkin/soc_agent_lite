from __future__ import annotations

from fastapi import APIRouter

from app.services.connectors import external_call, ExternalCallError

router = APIRouter()


@external_call()
def _failing_external() -> str:
    raise RuntimeError("forced failure for testing")


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/test-external")
def test_external() -> dict[str, str]:
    try:
        _failing_external()
    except ExternalCallError as e:  # pragma: no cover - demonstration endpoint
        return {"result": "failed", "error": str(e)}
    except RuntimeError as e:  # forced failure for testing path
        return {"result": "failed", "error": str(e)}
    return {"result": "ok"}
