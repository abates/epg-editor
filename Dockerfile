# syntax=docker/dockerfile:1
#
# Single multi-stage image for epg-editor: build the React frontend, then
# copy its static output into the Python/FastAPI backend image. One process
# (uvicorn) ends up serving the API, generated XMLTV, and (once the backend
# wires up static-file serving — not yet implemented, see CLAUDE.md's
# "Docker" section) the frontend. See CLAUDE.md's "Docker" section for the
# constraints this follows.

# ---------------------------------------------------------------------------
# Stage: frontend-build
# ---------------------------------------------------------------------------
# node:22-slim (Debian bookworm base) for glibc parity with the Python
# stage below, and because Node 22 is the current LTS line.
FROM node:22-slim AS frontend-build

WORKDIR /app/frontend

# Copy only the lockfile/manifest first so `npm ci` is cached as its own
# layer and doesn't re-run just because application source changed.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

# ---------------------------------------------------------------------------
# Stage: backend
# ---------------------------------------------------------------------------
# uv's own published image bundles a matching Python 3.12 + uv binary, which
# keeps "Python dependency management and builds: uv" (CLAUDE.md) true for
# the image build itself, not just local dev.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS backend

WORKDIR /app/backend

# Copy only the dependency manifests first for layer caching, same reasoning
# as the frontend stage above. `--no-install-project` skips building/
# installing the backend's own source (which isn't copied in yet) and
# installs just its third-party dependencies, so this layer stays cached
# across backend source changes that don't touch pyproject.toml/uv.lock.
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Now copy the actual backend source and install the project itself.
COPY backend/ ./
RUN uv sync --frozen --no-dev

# Pull in the built frontend assets from the first stage. Nothing in the
# backend serves these yet (no StaticFiles/SPA-fallback mount in
# app/main.py as of this writing) — this just stages the artifact at a
# path outside the backend source tree so that wiring, when it lands, has
# somewhere to point. See CLAUDE.md's "Docker" section.
COPY --from=frontend-build /app/frontend/dist /app/frontend/dist

# Bootstrap script: ensures /data/{config,cache,output} exist before the
# app starts (belt-and-suspenders alongside app.storage.ensure_data_dirs(),
# which the FastAPI lifespan already calls on startup).
COPY docker/entrypoint.sh /app/docker/entrypoint.sh
RUN chmod +x /app/docker/entrypoint.sh

EXPOSE 8080

ENTRYPOINT ["/app/docker/entrypoint.sh"]
# `--no-sync`: without it, plain `uv run` re-resolves/syncs the environment
# on every container start (and, since no --no-dev is implied, pulls in the
# dev dependency group — lxml/pytest/etc. — over the network). That defeats
# both "no dev deps in the shipped image" and offline startup, so pin it to
# exactly what `uv sync --frozen --no-dev` already installed at build time.
CMD ["uv", "run", "--no-sync", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
