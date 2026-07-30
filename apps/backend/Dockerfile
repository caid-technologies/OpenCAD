# syntax=docker/dockerfile:1

FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    OPENCAD_KERNEL_BACKEND=occt \
    OPENCAD_SOLVER_BACKEND=auto \
    OPENCAD_CORS_ALLOW_ORIGINS=http://localhost:5173,http://127.0.0.1:5173

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        libgl1 \
        libglib2.0-0 \
        libgomp1 \
        libsm6 \
        libxext6 \
        libxrender1 \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY apps/backend ./apps/backend

RUN python -m pip install --upgrade pip \
    && python -m pip install ".[full]"

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/kernel/healthz', timeout=3).read()" || exit 1

CMD ["python", "-m", "uvicorn", "api:app", "--app-dir", "apps/backend", "--host", "0.0.0.0", "--port", "8000"]
