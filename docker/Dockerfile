# Stage 1: Build the Next.js frontend
FROM node:22-slim AS frontend

WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

# Stage 2: Python application
FROM python:3.12-slim

WORKDIR /app

# Install uv for fast dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency metadata first (cache-friendly layer ordering)
COPY pyproject.toml uv.lock ./
COPY README.md ./

# Install dependencies
RUN uv sync --no-dev --frozen

# Copy application source
COPY src/ src/

# Copy frontend build from Stage 1
COPY --from=frontend /web/out web/out

# Consolidate all persistent data under /data
ENV SQUIRE_DB_PATH=/data/squire.db
ENV SQUIRE_SKILLS_PATH=/data/skills
ENV SQUIRE_KEYS_DIR=/data/keys
ENV SQUIRE_RISK_TOLERANCE=cautious

VOLUME ["/data"]
EXPOSE 8420

HEALTHCHECK --interval=30s --timeout=5s --retries=3 --start-period=10s \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8420/api/health')"]

ENTRYPOINT ["uv", "run", "squire"]
CMD ["web"]
