# SOC Agent Lite

A lightweight Security Operations (SecOps) incident assistant built with FastAPI. It ingests webhook events, persists incidents in Postgres, performs log queries, exposes real‑time WebSocket updates, and offers observability via Prometheus metrics.

This repository is suitable for local development and containerized deployment. It uses Alembic for database migrations and supports Redis for idempotency locks around incoming webhook processing.

## What systems it works with
- Operating systems: Linux, macOS, Windows (development). Docker images run on any Docker‑capable host.
- Runtime: Python 3.11+
- Services:
  - Postgres (async via asyncpg)
  - Redis (optional; used for idempotency)
  - Prometheus scrape endpoint (/metrics)
  - Web browser for interactive API docs at /docs

## Features
- FastAPI app with versioned routes under /api/v1
  - Health checks: GET /api/v1/health
  - Webhook ingestion: POST /api/v1/webhook (HMAC verification)
  - Incidents REST API: /api/v1/incidents
  - WebSocket: /api/v1/ws/incidents/{incident_id}
- Webhook signature verification via HMAC-SHA256 header X-Signature
- Multi-tenancy header X-Tenant enforced for write/read of incidents (see RLS section)
- Database migrations with Alembic
- Redis-backed idempotency helper to deduplicate requests
- Observability: Prometheus metrics mounted at /metrics

## Architecture (high level)
- app/main.py: FastAPI initialization, router registration, /docs exposure
- app/api/*: API routers (health, webhook, incidents, websocket)
- app/store/*: SQLAlchemy async engine/session and ORM models
- alembic/: Migration environment and versions
- app/services/*: Business logic (connectors, log query, ticketing, idempotency, workflow)
- app/observability/*: Metrics and instrumentation setup

## Quick start
You can run it either with Docker Compose (recommended) or locally with Python.

### 1) Using Docker Compose
Requirements: Docker and Docker Compose installed.

1. Copy environment file template and adjust values:
   cp .env.example .env
2. Start the stack:
   docker compose up --build
3. Open the docs in your browser:
   http://localhost:8000/docs

Notes:
- The app service runs Alembic migrations automatically at startup.
- Postgres and Redis services are included and wired via environment variables.

### 2) Run locally (without Docker)
Requirements: Python 3.11+, Postgres reachable, optional Redis.

1. Create and populate .env:
   cp .env.example .env
   # Edit DATABASE_URL and WEBHOOK_SECRET at minimum
2. Create a virtual environment and install dependencies:
   python -m venv .venv
   .venv\\Scripts\\activate  # Windows
   # or: source .venv/bin/activate  # macOS/Linux
   pip install -r requirements.txt
3. Create the database and run migrations:
   alembic upgrade head
4. Start the app:
   uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
5. Open the docs:
   http://127.0.0.1:8000/docs

## Environment variables
These are read from .env for local runs and can be provided via container envs in Docker.

Required:
- DATABASE_URL: SQLAlchemy async DSN, e.g. postgresql+asyncpg://user:pass@localhost:5432/app_db
- WEBHOOK_SECRET: Shared secret for HMAC verification of incoming webhooks

Optional (Redis for idempotency):
- REDIS_URL: e.g. redis://localhost:6379/0
- REDIS_HOST: default localhost
- REDIS_PORT: default 6379
- REDIS_USERNAME: optional
- REDIS_PASSWORD: optional
- REDIS_DB: default 0
- REDIS_TLS: set to true to enable TLS (default false)

Other notes:
- dotenv is loaded by app at startup and by Alembic; ensure .env is at project root.

## Using the webhook endpoint
1) Compute signature from raw body using the shared secret and send as header X-Signature: sha256=<hex>.

Example (Python):
from app.security.webhook_sign import sign_bytes
body = b'{"hello":"world"}'
print(sign_bytes(body, secret=b"your-secret"))  # prints 'sha256=<hex>'

Example (curl):
curl -X POST http://localhost:8000/api/v1/webhook/siem \
  -H "Content-Type: application/json" \
  -H "X-Signature: sha256=<hex>" \
  -H "X-Tenant: 11111111-2222-3333-4444-555555555555" \
  -d '{"source":"demo","type":"alert","severity":"high","entity":"srv-1","raw":{}}'

GET incident (tenant-filtered):
curl -s http://localhost:8000/api/v1/incidents/1 \
  -H "X-Tenant: 11111111-2222-3333-4444-555555555555"

## WebSocket test
A simple test page is provided: test_files/ws_test.html
- Update incident_id in the page and open it in the browser while the app is running.

## Database migrations
- Create a new revision: alembic revision -m "message"
- Autogenerate changes (ensure models are imported in alembic/env.py): alembic revision --autogenerate -m "message"
- Apply latest: alembic upgrade head

## Multi-tenancy and Row-Level Security (RLS)
This project is prepared for multi-tenant data isolation.

What is implemented in code:
- incidents table now has a mandatory tenant_id (UUID string) column.
- POST /api/v1/webhook/siem requires header X-Tenant and persists it into incidents. The header should contain a UUID (with or without dashes).
- GET /api/v1/incidents/{incident_id} requires header X-Tenant and only returns the incident if it belongs to that tenant.

Recommended Postgres RLS configuration:
1) Enable RLS on the incidents table and create a tenant policy using a session parameter app.tenant_id:

   ALTER TABLE incidents ENABLE ROW LEVEL SECURITY;
   CREATE POLICY tenant_isolation ON incidents
     USING (tenant_id = current_setting('app.tenant_id')::uuid);

2) Ensure tenant_id column type in Postgres is uuid. If you started with varchar(36) (default in initial code), you can migrate to uuid:

   ALTER TABLE incidents ALTER COLUMN tenant_id TYPE uuid USING tenant_id::uuid;
   CREATE INDEX IF NOT EXISTS ix_incidents_tenant_id ON incidents(tenant_id);

3) Set the session parameter for each request/connection in the application layer. Example using SQLAlchemy (async):

   from starlette.middleware.base import BaseHTTPMiddleware
   from sqlalchemy import text

   class TenantMiddleware(BaseHTTPMiddleware):
       async def dispatch(self, request, call_next):
           tenant = request.headers.get('X-Tenant')
           response = await call_next(request)
           return response

   # When creating a session/connection for a request:
   async with engine.connect() as conn:
       await conn.execute(text("SET app.tenant_id = :tid"), {"tid": tenant})

   # Or, set per-session after acquiring AsyncSession:
   await session.execute(text("SET app.tenant_id = :tid"), {"tid": tenant})

4) With RLS enabled and app.tenant_id set, Postgres will automatically restrict SELECT/INSERT/UPDATE/DELETE to rows where tenant_id matches the session setting.

Notes:
- Your app should validate that X-Tenant is a UUID and propagate it consistently.
- For cross-table enforcement (actions/evidence/tickets), you can either rely on application-level joins from incidents or extend schema to embed tenant_id and add additional RLS policies if those tables become directly queryable by clients.

## Troubleshooting
- Error: DATABASE_URL is not set. Define it in .env (or pass via env var) using asyncpg driver.
- Webhook returns 500 "Webhook secret is not configured": set WEBHOOK_SECRET in .env.
- Redis not available: idempotency features will fail; either configure REDIS_URL or disable features using it.
- Port already in use: adjust host/port when running uvicorn.

## License
This project is provided as-is for educational/demo purposes.
