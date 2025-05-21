# syntax=docker/dockerfile:1.4
FROM python:3.13-slim AS base

# ==================================

FROM base AS builder

RUN pip install --upgrade uv

WORKDIR /app

COPY pyproject.toml uv.lock ./

RUN python -m venv /app/.venv \
    && . /app/.venv/bin/activate \
    && uv sync --no-dev \
    && find /app/.venv -type d -name "__pycache__" -exec rm -r {} + 2>/dev/null || true \
    && find /app/.venv -type f -name "*.pyc" -delete \
    && find /app/.venv -type f -name "*.pyo" -delete \
    && find /app/.venv -type d -name "tests" -exec rm -r {} + 2>/dev/null || true \
    && find /app/.venv -type f -name "*.so" -exec strip {} + 2>/dev/null || true \
    && find /app/.venv -type d -name "pip" -exec rm -r {} + 2>/dev/null || true \
    && find /app/.venv -type d -name "wheel" -exec rm -r {} + 2>/dev/null || true \
    && find /app/.venv -type f -name "*.dist-info" -exec rm -r {} + 2>/dev/null || true \
    && find /app/.venv -type f -name "*.egg-info" -exec rm -r {} + 2>/dev/null || true

# Remove unnecessary files
RUN rm -rf /usr/share/doc/* && \
    rm -rf /usr/share/man/* && \
    rm -rf /usr/share/locale/* && \
    rm -rf /var/cache/* && \
    rm -rf /var/log/* && \
    rm -rf /var/lib/apt/lists/* && \
    rm -rf /usr/lib/python*/ensurepip && \
    rm -rf /usr/lib/python*/idlelib && \
    rm -rf /usr/lib/python*/distutils/command/*.exe

# ==================================
FROM base

LABEL org.opencontainers.image.source="https://github.com/kanniep/google-cloud-mcp-python"

WORKDIR /app

COPY src src
COPY --from=builder /app/.venv .venv

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH="/app"

ENTRYPOINT ["python", "src/main.py"]

EXPOSE 8080
