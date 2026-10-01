FROM python:3.10-slim AS builder

LABEL description="Heofberu Backend API -- BUILDER"

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /install

RUN pip install --no-cache-dir "poetry==2.1.3" "poetry-plugin-export==1.9.0"

COPY pyproject.toml poetry.lock* ./

RUN poetry export --without-hashes --format=requirements.txt --output=requirements.txt

RUN pip install --no-cache-dir --prefix=/install/deps -r requirements.txt

FROM python:3.10-slim

LABEL description="Heofberu Backend API"

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# REQUIRE_EXPLICIT_STAGE: refuse to start without STAGE instead of silently running as "dev".
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PATH=/usr/local/bin:$PATH \
    REQUIRE_EXPLICIT_STAGE=true

WORKDIR /app

RUN useradd --create-home --shell /bin/bash --uid 1000 app

# Only the installed dependencies are copied — no Poetry, no compilers, no build tools.
COPY --from=builder /install/deps /usr/local

COPY --chown=app:app . .
USER app

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl --fail http://localhost:8000/api/ping || exit 1

EXPOSE 8000

# Set RUN_MIGRATIONS=false on every replica but one (or run `alembic upgrade head` as a separate job)
# to avoid concurrent migration runs. `exec` makes the app PID 1 so it receives SIGTERM.
ENTRYPOINT ["sh", "-c"]
CMD ["if [ \"${RUN_MIGRATIONS:-true}\" != \"false\" ]; then alembic upgrade head; fi && exec python -m app.main"]
