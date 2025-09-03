from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
import uvicorn

from app.api.health import router as health_router
from app.api.webhook import router as webhook_router
from app.api.ws import router as ws_router
from app.api.incidents import router as incidents_router
from app.observability import setup_instrumentation

from fastapi.responses import JSONResponse, RedirectResponse

app = FastAPI()

# Setup observability (/metrics)
setup_instrumentation(app)

# Routers (versioned)
API_PREFIX = "/api/v1"
app.include_router(health_router, prefix=API_PREFIX, tags=["health"])
app.include_router(webhook_router, prefix=API_PREFIX, tags=["webhook"])
app.include_router(ws_router, prefix=API_PREFIX, tags=["ws"])
app.include_router(incidents_router, prefix=API_PREFIX, tags=["incidents"]) 

# Expose OpenAPI under /docs/openapi.json and redirect /docs/ to /docs
@app.get("/docs/openapi.json", include_in_schema=False)
async def openapi_under_docs():
    return JSONResponse(app.openapi())

@app.get("/docs/", include_in_schema=False)
async def docs_trailing_slash():
    return RedirectResponse(url="/docs")

if __name__ == "__main__":
    # This allows running the app directly: `python app/main.py`
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True, workers=1)
