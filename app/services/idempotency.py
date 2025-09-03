"""
Idempotency service backed by Redis.

try_lock(key, ttl=300): attempts to acquire a short-lived lock for the provided key.
- Returns True if the lock is acquired (first call).
- Returns False if the key already exists (subsequent calls until TTL expires).

Key source:
- Typically, the caller provides an Idempotency-Key header value.
- Alternatively, you can derive the key by hashing a request body (e.g., sha256 JSON).

Redis connection settings are read from environment variables with safe defaults.
This mirrors the example in temp.py but places it in a reusable service module.
"""
from __future__ import annotations

import hashlib
import os
from typing import Optional

from dotenv import load_dotenv
import redis

# Load variables from .env if present
load_dotenv()

# Read Redis configuration strictly from environment (.env or process env)
# Do not embed cloud credentials in code.
REDIS_URL = os.getenv("REDIS_URL")
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_USERNAME = os.getenv("REDIS_USERNAME") or None
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD") or None
REDIS_DB = int(os.getenv("REDIS_DB", "0"))
REDIS_TLS = os.getenv("REDIS_TLS", "false").lower() in ("1", "true", "yes")


def _get_redis_client() -> redis.Redis:
    """Create a Redis client configured via env vars.
    Using decode_responses=True to work with strings conveniently.
    Prefer REDIS_URL if provided; fallback to discrete params.
    """
    if REDIS_URL:
        return redis.from_url(REDIS_URL, decode_responses=True)
    return redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        username=REDIS_USERNAME,
        password=REDIS_PASSWORD,
        db=REDIS_DB,
        decode_responses=True,
        ssl=REDIS_TLS,
    )


_redis: Optional[redis.Redis] = None


def _client() -> redis.Redis:
    global _redis
    if _redis is None:
        _redis = _get_redis_client()
    return _redis


def try_lock(key: str, ttl: int = 300) -> bool:
    """Attempt to acquire an idempotency lock with SET NX EX.

    Args:
        key: The idempotency key. Typically the Idempotency-Key header, or a
             deterministic hash of the request body.
        ttl: Time-to-live for the lock in seconds (default 300).

    Returns:
        True if the lock was acquired (first request), False if it already exists.
    """
    if not key:
        # Treat empty key as non-lockable; refuse to acquire.
        return False

    # Namespacing the key to avoid collisions with other Redis usage
    redis_key = f"idempotency:{key}"

    # Redis-py exposes set() with nx/ex parameters
    # Returns True on success, None/False if not set
    res = _client().set(name=redis_key, value="1", nx=True, ex=ttl)
    return bool(res)


def body_hash(data: bytes | str) -> str:
    """Create a stable sha256 hex digest from request body to use as a key.
    Accepts bytes or string input.
    """
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()
