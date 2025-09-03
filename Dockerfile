# syntax=docker/dockerfile:1

FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# System deps for Playwright and asyncpg
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl gnupg ca-certificates \
    libnss3 libatk1.0-0 libatk-bridge2.0-0 libdrm2 libxkbcommon0 libxcomposite1 \
    libxdamage1 libxfixes3 libxrandr2 libasound2 libwayland-client0 libwayland-server0 \
    fonts-liberation libxshmfence1 libgbm1 libpango-1.0-0 libpangocairo-1.0-0 \
    libcairo2 libatspi2.0-0 libcurl4 gnupg2 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps
COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt \
    && python -m playwright install --with-deps chromium

# Copy app
COPY . .

# Expose uvicorn port
EXPOSE 8000

# Alembic config expects working dir at project root
ENV PYTHONPATH=/app

# Entrypoint script: run migrations then start uvicorn
CMD alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
