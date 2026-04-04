FROM python:3.12-slim

WORKDIR /app

# Install uv for fast dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency metadata first (cache-friendly layer ordering)
COPY pyproject.toml uv.lock ./
COPY packages/ packages/
COPY README.md ./

# Install dependencies
RUN uv sync --no-dev --frozen

# Copy application source
COPY src/ src/

# Default environment
ENV SQUIRE_RISK_PROFILE=cautious
ENV SQUIRE_DB_PATH=/data/squire.db

VOLUME ["/data"]

ENTRYPOINT ["uv", "run", "squire"]
CMD ["chat"]
