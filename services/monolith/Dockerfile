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

# Build context is backend root so both shared/ and services/monolith/ are accessible.
# shared/ must be COPY'd BEFORE pip install — requirements.txt has `-e ./shared`.
COPY services/monolith/requirements.txt .
COPY shared/ ./shared/
RUN python -m venv .venv && \
    .venv/bin/pip install --upgrade pip --quiet && \
    .venv/bin/pip install --no-cache-dir -r requirements.txt


# ── Stage 2: Runtime ──────────────────────────────────────────────────────────
# Reuse the same ARG so both stages stay in sync
ARG PYTHON_VERSION=3.12
FROM python:${PYTHON_VERSION}-slim AS runtime

# curl is used by the docker healthcheck against /health/ready
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Non-root user for security
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser

WORKDIR /app

# Copy venv from builder stage
COPY --from=builder /app/.venv .venv

# Copy monolith application source (not the whole backend root)
COPY services/monolith/ .

# Add venv to PATH so all commands use it
ENV PATH="/app/.venv/bin:$PATH"

# Switch to non-root user
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
