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

# Default environment
ENV SQUIRE_RISK_PROFILE=cautious
ENV SQUIRE_DB_PATH=/data/squire.db

# Strict host key checking requires known_hosts to exist; mount over /root/.ssh for persistence (#66)
RUN mkdir -p /root/.ssh && chmod 700 /root/.ssh && touch /root/.ssh/known_hosts

VOLUME ["/data"]

ENTRYPOINT ["uv", "run", "squire"]
CMD ["chat"]
