from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI

from app.api.health import router as health_router
from app.api.webhook import router as webhook_router
from app.api.ws import router as ws_router

app = FastAPI()

# Routers
app.include_router(health_router)
app.include_router(webhook_router)
app.include_router(ws_router)


if __name__ == "__main__":
    # This allows running the app directly: `python app/main.py`
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
