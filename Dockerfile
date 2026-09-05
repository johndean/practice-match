# syntax=docker/dockerfile:1.7
# Practice Match — one image for the api and worker services.
# Stage 1 builds the Vue app; stage 2 serves it from FastAPI. Railway populates
# declared ARGs from service variables: ENVIRONMENT (qa|production) drives the
# frontend's VITE_ENVIRONMENT; RAILWAY_GIT_COMMIT_SHA stamps only the runtime
# layer, as COMMIT_SHA (see below) — the frontend-build stage never receives it.
FROM node:22-bookworm-slim AS frontend-build
# No default: a build that ever fails to receive ENVIRONMENT must fail loudly here,
# not silently constant-fold the qa bundle (prototype jump bar included) into what
# ships to production (Task 8 finding, 2026-09-06).
ARG ENVIRONMENT
WORKDIR /work/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
ENV VITE_ENVIRONMENT=$ENVIRONMENT
RUN test -n "$ENVIRONMENT" || { echo "ENVIRONMENT build arg is required (qa|production)" >&2; exit 1; }
RUN npm run build

FROM python:3.12-slim-bookworm AS runtime
# ARG scope is per-stage; declared again here (still no default) so the same
# requirement holds even if this stage ever comes to consume it directly.
ARG ENVIRONMENT
# `railway up` builds are not git-connected, so RAILWAY_GIT_COMMIT_SHA is usually absent;
# scripts/deploy.sh sets the COMMIT_SHA service variable before each upload instead.
ARG COMMIT_SHA=dev
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    POETRY_VERSION=2.4.1 \
    POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_CREATE=false \
    PIP_NO_CACHE_DIR=1 \
    COMMIT_SHA=$COMMIT_SHA
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*
RUN pip install "poetry==${POETRY_VERSION}"
WORKDIR /app
COPY pyproject.toml poetry.lock ./
RUN poetry install --only main --no-root --no-cache
COPY app/ ./app/
COPY migrations/ ./migrations/
COPY scripts/ ./scripts/
COPY --from=frontend-build /work/frontend/dist/ ./frontend/dist/
# Nothing writes under /app at runtime (uvicorn and the Celery worker keep no
# files there; `migrate` only reads), so a non-root user is a plain drop of
# privilege — no volume or writable-path accommodation needed.
RUN useradd --system --uid 10001 --create-home --shell /usr/sbin/nologin app && chown -R app:app /app
EXPOSE 8000
USER app
ENTRYPOINT ["bash", "scripts/start.sh"]
CMD ["api"]
