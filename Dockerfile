# =============================================================================
# Phase4B Test Project - Production Dockerfile
# =============================================================================
# Multi-stage build for optimized production deployment of ADWS
# (AI Developer Workflow System)
#
# Build: docker build -t phase4b_test:latest .
# Run:   docker run -p 8000:8000 phase4b_test:latest
# =============================================================================

# -----------------------------------------------------------------------------
# Stage 1: Builder
# Build dependencies and prepare application
# -----------------------------------------------------------------------------
FROM python:3.11-slim AS builder

# Set build arguments
ARG DEBIAN_FRONTEND=noninteractive

# Install build dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /build

# Copy dependency files first (for better caching)
COPY requirements.txt pyproject.toml ./
COPY README.md ./

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY adws/ ./adws/
COPY agents/ ./agents/

# Install the package
RUN pip install --no-cache-dir -e .

# -----------------------------------------------------------------------------
# Stage 2: Runtime
# Minimal production image
# -----------------------------------------------------------------------------
FROM python:3.11-slim AS runtime

# Set runtime arguments
ARG DEBIAN_FRONTEND=noninteractive
ARG ADWS_VERSION=2.0.0

# Add labels for container metadata
LABEL maintainer="Etherea Logic"
LABEL version="${ADWS_VERSION}"
LABEL description="AI Developer Workflow System - Production Deployment"
LABEL org.opencontainers.image.source="https://github.com/Org-EthereaLogic/ADWS_UV_Cookiecutter_v2.0"
LABEL org.opencontainers.image.title="Phase4B Test Project"
LABEL org.opencontainers.image.version="${ADWS_VERSION}"
LABEL service="phase4b_test"

# Install runtime dependencies only
RUN apt-get update && apt-get install -y \
    git \
    curl \
    ca-certificates \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for security
RUN groupadd -r adws --gid=1000 && \
    useradd -r -g adws --uid=1000 --home-dir=/app --shell=/bin/bash adws && \
    mkdir -p /app && \
    chown -R adws:adws /app

# Set working directory
WORKDIR /app

# Copy Python dependencies from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY --chown=adws:adws adws/ ./adws/
COPY --chown=adws:adws agents/ ./agents/
COPY --chown=adws:adws pyproject.toml README.md ./

# Copy dashboards and documentation (optional for runtime)
COPY --chown=adws:adws dashboards/ ./dashboards/

# Create necessary directories with proper permissions
RUN mkdir -p .adws/state .adws/events logs && \
    chown -R adws:adws .adws logs

# Switch to non-root user
USER adws

# Environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    ADWS_LOG_LEVEL=INFO \
    ADWS_METRICS_ENABLED=true \
    ADWS_HEALTH_CHECKS_ENABLED=true \
    ADWS_API_HOST=0.0.0.0 \
    ADWS_API_PORT=8000 \
    ADWS_WORKSPACE_DIR=/app/.adws \
    ADWS_DB_PATH=/app/.adws/state/workflows.db \
    ADWS_EVENT_BUS_DIR=/app/.adws/events

# Expose API port
EXPOSE 8000

# Health check using the built-in health endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/healthz || exit 1

# Default command: Run Uvicorn server
CMD ["uvicorn", "adws.api.server:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--log-level", "info", \
     "--access-log", \
     "--no-use-colors"]

# Alternative commands:
# For Gunicorn with multiple workers (production):
# CMD ["gunicorn", "adws.api.server:app", "-w", "4", "-k", "uvicorn.workers.UvicornWorker", "-b", "0.0.0.0:8000"]
#
# For TUI mode:
# CMD ["python", "-m", "adws.tui.app"]
