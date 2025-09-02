"""Observability package.

Provides Prometheus metrics via prometheus-fastapi-instrumentator and custom metrics.

This package's __init__ is only for imports/re-exports.
"""

from .metrics import webhook_incoming_counter, workflow_duration_seconds
from .setup import setup_instrumentation
