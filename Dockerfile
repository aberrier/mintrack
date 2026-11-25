# syntax=docker/dockerfile:1

# --- The Angular app, built once on the build platform: its output is the same for every target.
FROM --platform=$BUILDPLATFORM node:24-slim@sha256:dc26ae92c9fb15cf6b1d63e20f0944b2efe0f115b20e00be48fb23fceb061c54 AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# --- uv
FROM ghcr.io/astral-sh/uv:0.13.10@sha256:a3ea1357342c1a4bf9a0c53a3deb1b55379aefa037338d8113d5771efa01774f AS uv

# --- The Python virtualenv, on the same base image as the runtime.
FROM python:3.15-slim-trixie@sha256:65a65fc7b30b06cb6df4930fd4650697cb23f4c2698ab81fc87e4b031bc36928 AS backend
COPY --from=uv /uv /usr/local/bin/uv
# Bytecode is compiled at build time, as the runtime file system is read-only.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv
WORKDIR /src
COPY pyproject.toml uv.lock README.md LICENSE ./
RUN uv sync --locked --no-default-groups --no-install-project
COPY src ./src
RUN uv sync --locked --no-default-groups --no-editable

# --- Runtime: the virtualenv and the built app.
FROM python:3.15-slim-trixie@sha256:65a65fc7b30b06cb6df4930fd4650697cb23f4c2698ab81fc87e4b031bc36928
ARG COMMIT=unknown
LABEL org.opencontainers.image.description="A minimal, self-hosted TV and movie tracker" \
      org.opencontainers.image.source="https://github.com/aberrier/mintrack" \
      org.opencontainers.image.licenses="AGPL-3.0-only"

RUN useradd --uid 10001 --user-group --no-create-home --shell /usr/sbin/nologin mintrack
COPY --from=backend /app/.venv /app/.venv
COPY --from=frontend /build/dist/frontend/browser /app/frontend

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    MINTRACK__PROJECT__ENVIRONMENT=prod \
    MINTRACK__PROJECT__COMMIT="${COMMIT}" \
    MINTRACK__SERVER__HOST=0.0.0.0 \
    MINTRACK__SERVER__FRONTEND_DIST=/app/frontend

USER 10001
WORKDIR /app
EXPOSE 8000
# mintrack healthcheck queries /api/health (slim images have no curl or wget).
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 CMD ["mintrack", "healthcheck"]
CMD ["mintrack", "server"]
