FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.10 /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# Dependencies first so code edits don't invalidate this layer.
COPY pyproject.toml uv.lock ./
# The Agent SDK wheel (113 MB, bundles the Claude CLI) is fetched on the host into vendor/ by
# scripts/fetch-agent-sdk.sh, because uv cannot resume an interrupted download.
ARG SDK_WHEEL=claude_agent_sdk-0.2.166-py3-none-manylinux_2_17_aarch64.whl
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=vendor,target=/wheels \
    uv sync --frozen --no-dev --no-install-project --no-install-package claude-agent-sdk \
 && uv pip install --python /opt/venv/bin/python --no-deps /wheels/$SDK_WHEEL

COPY app ./app
COPY web ./web
COPY data/mock_instamart.json ./data/mock_instamart.json

RUN useradd --create-home --uid 1000 anyaa \
    && mkdir -p /app/data /app/logs /app/web/audio \
    && chown -R anyaa:anyaa /app
USER anyaa

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
