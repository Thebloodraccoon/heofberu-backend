FROM python:3.10.13-slim AS builder

LABEL description="Heofberu Backend API -- BUILDER"

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /install

RUN pip install --no-cache-dir poetry poetry-plugin-export

COPY pyproject.toml poetry.lock* ./

RUN poetry export --without-hashes --format=requirements.txt --output=requirements.txt

RUN pip install --no-cache-dir --prefix=/install/deps -r requirements.txt

FROM python:3.10.13-slim

LABEL description="Heofberu Backend API"

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PATH=/usr/local/bin:$PATH

WORKDIR /app

RUN useradd --create-home --shell /bin/bash --uid 1000 app \
    && chown -R app:app /app

# Only the installed dependencies are copied — no Poetry, no compilers, no build tools.
COPY --from=builder /install/deps /usr/local

COPY --chown=app:app . .
USER app

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl --fail http://localhost:8000/api/ping || exit 1

EXPOSE 8000

ENTRYPOINT ["sh", "-c"]
CMD ["alembic upgrade head && python -m app.main"]