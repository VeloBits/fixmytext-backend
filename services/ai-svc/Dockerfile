# ┌─────────────────────────────────────────────────────────────────────────────┐
# │  services/ai-svc/Dockerfile                                                 │
# │                                                                             │
# │  Stage 1 (builder) : create .venv and install dependencies                 │
# │  Stage 2 (runtime) : copy .venv + source, run as non-root user             │
# └─────────────────────────────────────────────────────────────────────────────┘

# ── Stage 1: Dependency builder ───────────────────────────────────────────────
ARG PYTHON_VERSION=3.12
FROM python:${PYTHON_VERSION}-slim AS builder

LABEL org.opencontainers.image.title="FixMyText AI Service"
LABEL org.opencontainers.image.description="FastAPI Groq-backed AI text transformation service"

WORKDIR /app

# Build context is backend root so both shared/ and services/ai-svc/ are accessible.
# shared/ must be COPY'd BEFORE pip install - requirements.txt has `-e ./shared`.
COPY services/ai-svc/requirements.txt .
COPY shared/ ./shared/
RUN python -m venv .venv && \
    .venv/bin/pip install --upgrade pip setuptools wheel --quiet && \
    .venv/bin/pip install --no-cache-dir --no-build-isolation -r requirements.txt && \
    .venv/bin/pip install --no-cache-dir --no-deps arq==0.28.0


# ── Stage 2: Runtime ──────────────────────────────────────────────────────────
ARG PYTHON_VERSION=3.12
FROM python:${PYTHON_VERSION}-slim AS runtime

# Release version injected by the CD pipeline; defaults to a dev marker for
# local builds so settings.VERSION (read from env VERSION) never lies.
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

# Copy ai-svc application source
COPY services/ai-svc/ .

# Add venv to PATH so all commands use it
ENV PATH="/app/.venv/bin:$PATH"

# Switch to non-root user
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
