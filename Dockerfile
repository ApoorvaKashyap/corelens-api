# --- Stage 1: builder ---
FROM python:3.14-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv
WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

COPY pyproject.toml uv.lock ./
RUN uv lock --upgrade-package core-lens
RUN uv sync --frozen --no-dev --no-install-project

COPY . .
RUN uv sync --frozen --no-dev

# --- Stage 2: runtime ---
FROM python:3.14-slim
RUN useradd -m -u 1000 appuser
WORKDIR /app
COPY --from=builder --chown=appuser:appuser /app /app
RUN mkdir -p /app/.logs && chown -R appuser:appuser /app


ENV PATH="/app/.venv/bin:$PATH"

USER appuser
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/v1/meta/health')"

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]