# Domovoy — HOA requests bot (long-polling worker, no exposed ports)
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Dependencies first, for layer caching
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

COPY src ./src
RUN uv sync --frozen --no-dev

# Run unprivileged; /data is the mounted volume for the SQLite file
RUN useradd --create-home --uid 10001 bot \
    && mkdir -p /data \
    && chown bot:bot /data
USER bot

ENV DB_PATH=/data/domovoy.db

CMD ["uv", "run", "--frozen", "--no-dev", "python", "-m", "domovoy"]
