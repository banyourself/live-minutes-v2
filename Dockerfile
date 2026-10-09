FROM node:22-slim@sha256:43ac6c60b8f89723f746e8a92ce91abd5017e627ce1ddfe4238355d3a30b772c AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

FROM python:3.14-slim@sha256:f85c5697265c178cc6887276c55fe16cf3d14ca35c3df6a5eab3b360534a55d2
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 \
    WEB_DIST=/app/web/dist STORAGE_DIR=/data/files AUTO_CREATE_TABLES=0 INLINE_WORKER=0
WORKDIR /app
RUN apt-get update && apt-get upgrade -y --no-install-recommends && rm -rf /var/lib/apt/lists/*
COPY server/requirements.txt server/requirements.txt
RUN pip install --require-hashes --no-deps -r server/requirements.txt && python -m pip uninstall -y pip
COPY zoom_minutes.py ./
COPY docs/AI-REFERENCE.md docs/AI-REFERENCE.md
COPY minutes_app/ minutes_app/
COPY server/ server/
COPY --from=web /web/dist web/dist
RUN useradd --create-home --uid 10001 app && mkdir -p /data/files && chown -R app /data
USER 10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/api/health' % os.environ.get('PORT', '8000'), timeout=4)"
CMD ["sh", "-c", "if [ \"${RUN_MIGRATIONS:-1}\" = \"1\" ]; then python -m alembic -c server/alembic.ini upgrade head || exit 1; fi; exec uvicorn server.asgi:app --host 0.0.0.0 --port ${PORT:-8000} --no-proxy-headers --no-server-header --workers ${WEB_CONCURRENCY:-2}"]
