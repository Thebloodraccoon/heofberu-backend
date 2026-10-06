FROM python:3.10-slim AS builder

LABEL description="Heofberu Backend API -- BUILDER"

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.10.11 /uv /usr/local/bin/uv

ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1

WORKDIR /install

COPY pyproject.toml uv.lock* ./

RUN uv sync --no-dev --no-install-project

FROM python:3.10-slim

LABEL description="Heofberu Backend API"

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PATH=/opt/venv/bin:/usr/local/bin:$PATH \
    REQUIRE_EXPLICIT_STAGE=true

WORKDIR /app

RUN useradd --create-home --shell /bin/bash --uid 1000 app

COPY --from=builder /opt/venv /opt/venv

COPY --chown=app:app . .
USER app

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl --fail http://localhost:8000/api/v1/ping || exit 1

EXPOSE 8000

ENTRYPOINT ["sh", "-c"]
CMD ["if [ \"${RUN_MIGRATIONS:-true}\" != \"false\" ]; then alembic upgrade head; fi && exec python -m app.main"]
