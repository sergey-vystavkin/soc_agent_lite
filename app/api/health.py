from fastapi import APIRouter, Header, Request, HTTPException, Depends
from typing import Optional

from app.services.idempotency import try_lock, body_hash
from app.security.webhook_sign import verify_webhook_signature

router = APIRouter()


@router.get("/health")
async def health() -> dict:
    """Health-check endpoint returning a simple ok flag."""
    return {"ok": True}


@router.get("/idem-check")
async def idem_check(request: Request, idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key")) -> dict:
    """Demo endpoint to verify idempotency behavior.
    - If Idempotency-Key header is provided, it is used as the key.
    - Otherwise, we hash the raw body as the key.

    First call with a key returns 200 and {acquired: true}.
    Subsequent call before TTL expires returns 409.
    """
    raw = await request.body()
    key = idempotency_key or body_hash(raw or b"null")

    if try_lock(key, ttl=30):
        return {"acquired": True, "key": key}

    # Already processed (or in progress)
    raise HTTPException(status_code=409, detail={"acquired": False, "key": key})


@router.post("/webhook-test")
async def webhook_test(
    request: Request,
    _=Depends(verify_webhook_signature),
) -> dict:
    """Test endpoint to validate webhook signature verification.

    Send any body with header:
    - X-Signature: sha256=<hex>

    Returns the sha256 hex of the received body on success.
    """
    body = await request.body()
    # Return computed signature and echo size for convenience
    return {
        "ok": True,
        "received_bytes": len(body),
        "expected_header": "sha256=<hex>",
    }
