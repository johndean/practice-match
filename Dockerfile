# syntax=docker/dockerfile:1.7
# Practice Match — one image for the api and worker services.
# Stages 1–2 build the two frontends; stage 3 serves the one SITE_MODE selects. Railway populates
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

# The VIN Foundation Coming Soon page (John's Vue project, coming-soon/): built into the
# same image and served by the api when SITE_MODE=coming_soon (production until launch).
FROM node:22-bookworm-slim AS coming-soon-build
WORKDIR /work/coming-soon
COPY coming-soon/package.json coming-soon/package-lock.json ./
RUN npm ci
COPY coming-soon/ ./
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
# The eighteen demo hospitals and their photographs (spec 2026-09-06 D3/D7): the `seed` role
# reads seeds/hospitals.json in-container, and GET /api/listings/{id}/photos/{n} serves the
# committed WebP files from seeds/hospitals/photos/. ~4.1 MiB (110 files).
COPY seeds/ ./seeds/
COPY --from=frontend-build /work/frontend/dist/ ./frontend/dist/
COPY --from=coming-soon-build /work/coming-soon/dist/ ./coming-soon/dist/
# /app/BUILD_SHA is what /api/healthz reports as commit_sha: scripts/deploy.sh writes the
# source's short sha into the `git archive` it uploads, so the stamp travels with the tree
# and cannot be set independently of it the way the COMMIT_SHA variable can (P14).
# `BUILD_SH[A]` makes it optional — the glob matches nothing on a build whose context has
# no stamp (a local scripts/verify-image.sh, or a git-connected Railway build). It must
# stay PAIRED with a source that is always present: a COPY whose only source matches
# nothing fails outright ("COPY failed: no source files were specified", measured
# 2026-09-07 on the CLASSIC builder, which is what a local scripts/verify-image.sh uses;
# Railway builds with BuildKit, where an empty wildcard is tolerated rather than fatal — so
# the paired form is never worse there, and on Railway the stamp is always present anyway).
# pyproject.toml is the pairing — already copied above, same content, so this
# adds nothing to the image, and being the last layer it never invalidates poetry install.
COPY pyproject.toml BUILD_SH[A] ./
# Nothing writes under /app at runtime (uvicorn and the Celery worker keep no
# files there; `migrate` only reads), so a non-root user is a plain drop of
# privilege — no volume or writable-path accommodation needed.
RUN useradd --system --uid 10001 --create-home --shell /usr/sbin/nologin app && chown -R app:app /app
EXPOSE 8000
USER app
ENTRYPOINT ["bash", "scripts/start.sh"]
CMD ["api"]
