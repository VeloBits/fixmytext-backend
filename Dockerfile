# ┌─────────────────────────────────────────────────────────────────────────────┐
# │  backend/Dockerfile                                                         │
# │                                                                             │
# │  Stage 1 (builder) : create .venv and install dependencies                 │
# │  Stage 2 (runtime) : copy .venv + source, run as non-root user             │
# └─────────────────────────────────────────────────────────────────────────────┘

# ── Stage 1: Dependency builder ───────────────────────────────────────────────
ARG PYTHON_VERSION=3.12
FROM python:${PYTHON_VERSION}-slim AS builder

LABEL org.opencontainers.image.title="FixMyText Backend"
LABEL org.opencontainers.image.description="FastAPI text transformation service"

WORKDIR /app

# Create venv and install dependencies into it
COPY requirements.txt .
RUN python -m venv .venv && \
    .venv/bin/pip install --upgrade pip --quiet && \
    .venv/bin/pip install --no-cache-dir -r requirements.txt


# ── Stage 2: Runtime ──────────────────────────────────────────────────────────
# Reuse the same ARG so both stages stay in sync
ARG PYTHON_VERSION=3.12
FROM python:${PYTHON_VERSION}-slim AS runtime

# Release version injected by the CD pipeline; defaults to a dev marker for
# local builds so settings.VERSION (read from env VERSION) never lies.
ARG APP_VERSION=0.0.0-dev
ENV VERSION=${APP_VERSION}
LABEL org.opencontainers.image.version=${APP_VERSION}

# curl is used by the docker healthcheck against /health/ready
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Non-root user for security
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser

WORKDIR /app

# Copy venv from builder stage
COPY --from=builder /app/.venv .venv

# Copy application source
COPY . .

# Add venv to PATH so all commands use it
ENV PATH="/app/.venv/bin:$PATH"

# Switch to non-root user
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
