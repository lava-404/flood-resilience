# Build context = services/ ... but fixtures and migrations live at repo root, so build from the REPO ROOT:
#   docker build -f services/Dockerfile --target api -t floodres-api:$(git rev-parse --short HEAD) .
# UNTESTED (no Docker in the authoring environment).
FROM python:3.12-slim AS base
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/services/common:/app/services/forecast:/app/services/ingest:/app/services/api
WORKDIR /app
COPY services/requirements.txt services/requirements.txt
RUN pip install --no-cache-dir -r services/requirements.txt
COPY services services
COPY data/fixtures data/fixtures
COPY infra/db/migrations infra/db/migrations
RUN useradd -r -u 10001 app && chown -R app /app
USER app

FROM base AS api
ENV FIXTURE_PATH=/app/data/fixtures/replay_sep2024_SYNTHETIC.json
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --retries=3 CMD python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/healthz', timeout=2)"
CMD ["uvicorn", "app.asgi:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]

FROM base AS ingest
ENV FIXTURE_PATH=/app/data/fixtures/replay_sep2024_SYNTHETIC.json
CMD ["python", "-m", "ingest"]

FROM base AS forecast
CMD ["python", "-m", "floodres.sqs_worker"]

FROM base AS migrate
CMD ["python", "-m", "floodcommon.migrate"]
