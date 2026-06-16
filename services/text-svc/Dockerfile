# ┌─────────────────────────────────────────────────────────────────────────────┐
# │  services/text-svc/Dockerfile                                               │
# │                                                                             │
# │  Stage 1 (builder) : create .venv and install dependencies                 │
# │  Stage 2 (runtime) : copy .venv + source, run as non-root user             │
# └─────────────────────────────────────────────────────────────────────────────┘

# ── Stage 1: Dependency builder ───────────────────────────────────────────────
ARG PYTHON_VERSION=3.12
FROM python:${PYTHON_VERSION}-slim AS builder

LABEL org.opencontainers.image.title="FixMyText Text Service"
LABEL org.opencontainers.image.description="FastAPI local text transformation service"

WORKDIR /app

# Build context is backend root so both shared/ and services/text-svc/ are accessible.
# shared/ must be COPY'd BEFORE pip install — requirements.txt has `-e ./shared`.
COPY services/text-svc/requirements.txt .
COPY shared/ ./shared/
RUN python -m venv .venv && \
    .venv/bin/pip install --upgrade pip --quiet && \
    .venv/bin/pip install --no-cache-dir -r requirements.txt


# ── Stage 2: Runtime ──────────────────────────────────────────────────────────
ARG PYTHON_VERSION=3.12
FROM python:${PYTHON_VERSION}-slim AS runtime

# Release version injected by CD pipeline
ARG APP_VERSION=0.0.0-dev
ENV VERSION=${APP_VERSION}
LABEL org.opencontainers.image.version=${APP_VERSION}

# Apply available OS security patches (e.g. openssl) so the base image's fixable
# CVEs don't trip the CI Trivy gate. Runs as root before dropping privileges.
RUN apt-get update && apt-get upgrade -y && rm -rf /var/lib/apt/lists/*

# Non-root user for security
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser

WORKDIR /app

# Copy venv from builder stage
COPY --from=builder /app/.venv .venv

# Copy shared package (needed for editable install at runtime)
COPY --from=builder /app/shared ./shared

# Copy text-svc application source
COPY services/text-svc/ .

# Add venv to PATH so all commands use it
ENV PATH="/app/.venv/bin:$PATH"

# Switch to non-root user
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# Multiple workers so one CPU-bound tool request can't wedge the whole service
# (paired with per-request wall-clock bounds on heavy tools). Override via
# WEB_CONCURRENCY at deploy time to match the container's CPU allocation.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
