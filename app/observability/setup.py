from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator


def setup_instrumentation(app: FastAPI) -> None:
    """Attach Prometheus instrumentation to FastAPI app and expose /metrics.

    - Standard app metrics (latency, requests, etc.)
    - /metrics endpoint
    """
    instrumentator = Instrumentator(
        excluded_handlers=[],
        should_group_status_codes=True,
        should_ignore_untemplated=True,
        should_instrument_requests_inprogress=True,
    )
    instrumentator.instrument(app)
    instrumentator.expose(app, include_in_schema=False, endpoint="/metrics")
