# syntax=docker/dockerfile:1

# ---- Stage 1: build the React app --------------------------------------------------
FROM node:22-alpine AS frontend
WORKDIR /frontend
# Dependencies first so this layer is cached until package-lock.json changes.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build


# ---- Stage 2: Python runtime (no Node, no node_modules) ----------------------------
FROM python:3.12-slim AS runtime

COPY --from=ghcr.io/astral-sh/uv:0.13.6 /uv /usr/local/bin/uv

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app/backend

# Install locked dependencies before copying the code so code changes reuse this layer.
COPY backend/pyproject.toml backend/uv.lock backend/.python-version ./
RUN uv sync --frozen --no-dev --no-install-project

COPY backend/ ./
COPY --from=frontend /frontend/dist /app/frontend/dist

ENV FRONTEND_DIST=/app/frontend/dist \
    DJANGO_MEDIA_ROOT=/data/media

# Settings refuse to load without a secret key when DEBUG is off; collectstatic needs none.
RUN DJANGO_SECRET_KEY=collectstatic-only python manage.py collectstatic --noinput

# Run as an unprivileged user; /data/media is mounted as a volume for uploads.
RUN useradd --create-home --uid 1000 app \
    && mkdir -p /data/media \
    && chown -R app:app /data
USER app

EXPOSE 8000
ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["gunicorn", "--config", "gunicorn.conf.py", "config.wsgi:application"]
