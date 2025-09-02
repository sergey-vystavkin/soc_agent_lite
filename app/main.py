from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
import uvicorn

from app.api.health import router as health_router
from app.api.webhook import router as webhook_router
from app.api.ws import router as ws_router
from app.api.incidents import router as incidents_router
from app.observability import setup_instrumentation

app = FastAPI()

# Setup observability (/metrics)
setup_instrumentation(app)

# Routers
app.include_router(health_router)
app.include_router(webhook_router)
app.include_router(ws_router)
app.include_router(incidents_router)


if __name__ == "__main__":
    # This allows running the app directly: `python app/main.py`
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True, workers=1)
