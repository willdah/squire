FROM python:3.12-slim

WORKDIR /app

# Install uv for fast dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy project files
COPY pyproject.toml uv.lock* ./
COPY src/ src/
COPY README.md ./

# Install dependencies
RUN uv sync --no-dev --frozen

# Default environment
ENV SQUIRE_RISK_PROFILE=cautious
ENV SQUIRE_DB_PATH=/data/squire.db

VOLUME ["/data"]

ENTRYPOINT ["uv", "run", "squire"]
CMD ["chat"]
