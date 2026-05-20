# ┌─────────────────────────────────────────────────────────────────────────────┐
# │  services/account-svc/Dockerfile                                           │
# │                                                                             │
# │  Stage 1 (builder) : create .venv and install dependencies                 │
# │  Stage 2 (runtime) : copy .venv + source, run as non-root user             │
# └─────────────────────────────────────────────────────────────────────────────┘

# ── Stage 1: Dependency builder ───────────────────────────────────────────────
ARG PYTHON_VERSION=3.12
FROM python:${PYTHON_VERSION}-slim AS builder

LABEL org.opencontainers.image.title="FixMyText Account Service"
LABEL org.opencontainers.image.description="FastAPI service for user account data: preferences, history, share."

WORKDIR /app

# Build context is backend root so both shared/ and services/account-svc/ are accessible.
# shared/ must be COPY'd BEFORE pip install — requirements.txt has `-e ./shared`.
COPY services/account-svc/requirements.txt .
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

# Non-root user for security
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser

WORKDIR /app

# Copy venv from builder stage
COPY --from=builder /app/.venv .venv

# Copy shared package (needed for editable install at runtime)
COPY --from=builder /app/shared ./shared

# Copy account-svc application source
COPY services/account-svc/ .

# Add venv to PATH so all commands use it
ENV PATH="/app/.venv/bin:$PATH"

# Switch to non-root user
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
