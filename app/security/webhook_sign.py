"""
Webhook signature verification utilities.

- Reads WEBHOOK_SECRET from environment (.env supported).
- Computes and verifies HMAC-SHA256 signature over the raw HTTP body.
- Compares with the `X-Signature` header of the form `sha256=<hex>` using
  `hmac.compare_digest` to avoid timing attacks.

Usage with FastAPI:

    from fastapi import APIRouter, Depends, Request
    from app.security.webhook_sign import verify_webhook_signature

    router = APIRouter()

    @router.post("/webhook")
    async def webhook_endpoint(
        request: Request,
        _=Depends(verify_webhook_signature),  # will raise 401 if invalid
    ):
        # process body
        data = await request.body()
        return {"ok": True}

Manual usage inside a handler:

    from app.security.webhook_sign import ensure_valid_signature

    async def handler(request: Request):
        await ensure_valid_signature(request)  # raises HTTPException(401) on mismatch
        ...

Testing with curl:
1) Generate signature locally (Python):

    from app.security.webhook_sign import sign_bytes
    body = b'{"hello":"world"}'
    print(sign_bytes(body))  # prints 'sha256=<hex>'

2) Send with correct signature:

    curl -X POST http://localhost:8000/webhook \
         -H "Content-Type: application/json" \
         -H "X-Signature: sha256=<hex_from_python>" \
         -d '{"hello":"world"}'

3) Send with wrong signature (change a char) -> should return 401.
"""
from __future__ import annotations

import hmac
import os
import re
from hashlib import sha256
from typing import Optional

from dotenv import load_dotenv
from fastapi import HTTPException, Request, status

# Load environment variables from .env if present
load_dotenv()

WEBHOOK_SECRET: Optional[str] = os.getenv("WEBHOOK_SECRET")

_SIG_PREFIX = "sha256="
_SIG_HEADER = "X-Signature"
_SIG_RE = re.compile(r"^sha256=([0-9a-fA-F]{64})$")


def _require_secret() -> bytes:
    """Get the webhook secret as bytes, raising 500 if not configured."""
    if not WEBHOOK_SECRET:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Webhook secret is not configured",
        )
    return WEBHOOK_SECRET.encode("utf-8")


def sign_bytes(body: bytes, secret: Optional[bytes | str] = None) -> str:
    """Compute HMAC-SHA256 signature string for given body.

    Returns the full header value form: 'sha256=<hex>'.
    """
    if isinstance(secret, str):
        secret = secret.encode("utf-8")
    key = secret if secret is not None else _require_secret()
    mac = hmac.new(key, body, sha256).hexdigest()
    return f"{_SIG_PREFIX}{mac}"


def parse_signature_header(value: Optional[str]) -> Optional[str]:
    """Extract hex digest from header value 'sha256=<hex>'.
    Returns the hex digest (lower/upper accepted) or None if format invalid.
    """
    if not value:
        return None
    m = _SIG_RE.match(value.strip())
    if not m:
        return None
    return m.group(1).lower()


async def read_raw_body(request: Request) -> bytes:
    """Read the raw body bytes without JSON parsing.

    Note: In Starlette/FastAPI, request.body() buffers the content so it can be
    awaited multiple times within the same request lifecycle.
    """
    return await request.body()


async def ensure_valid_signature(request: Request) -> None:
    """Validate the request's HMAC-SHA256 signature.

    - Reads raw body
    - Computes HMAC using WEBHOOK_SECRET
    - Compares to X-Signature header using hmac.compare_digest
    - Raises HTTPException(401) on mismatch
    """
    header_value = request.headers.get(_SIG_HEADER)
    provided_hex = parse_signature_header(header_value)
    if not provided_hex:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing or invalid signature header")

    body = await read_raw_body(request)
    expected_full = sign_bytes(body)
    # expected_full is 'sha256=<hex>'; we compare the hex digests only
    expected_hex = expected_full.split("=", 1)[1]

    if not hmac.compare_digest(provided_hex, expected_hex):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Signature mismatch")


# FastAPI dependency wrapper
async def verify_webhook_signature(request: Request) -> None:
    await ensure_valid_signature(request)
