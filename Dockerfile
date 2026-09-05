# syntax=docker/dockerfile:1.7
# Practice Match — one image for the api and worker services.
# Stage 1 builds the Vue app; stage 2 serves it from FastAPI. Railway populates
# declared ARGs from service variables: ENVIRONMENT (qa|production) drives the
# frontend's VITE_ENVIRONMENT; RAILWAY_GIT_COMMIT_SHA stamps both layers.
FROM node:22-bookworm-slim AS frontend-build
ARG ENVIRONMENT=qa
WORKDIR /work/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
ENV VITE_ENVIRONMENT=$ENVIRONMENT
RUN npm run build

FROM python:3.12-slim-bookworm AS runtime
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
EXPOSE 8000
ENTRYPOINT ["bash", "scripts/start.sh"]
CMD ["api"]
