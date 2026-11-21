# ---------------------------------------------------------------------------
# Backend (API) image - FastAPI + psycopg
# Pinned base image version: not "latest", so the build is reproducible.
# ---------------------------------------------------------------------------
FROM python:3.12.8-slim

# The version is set at build time: docker build --build-arg APP_VERSION=1.0.1 ...
ARG APP_VERSION=1.0.0
ENV APP_VERSION=${APP_VERSION} \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Copy and install the dependencies first: this layer gets cached, so when
# only the code changes, pip install does not run again.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

# Security: do not run the application as root.
RUN useradd --create-home --uid 10001 appuser
USER appuser

EXPOSE 8000

# 2 worker processes inside one container; the "real" scaling comes from Swarm replicas.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
