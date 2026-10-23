# Multi-stage production Dockerfile for Maps4U Street Map System (Stage 6 S6.T1)
FROM python:3.13-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    fonts-dejavu-core \
    gdal-bin \
    libgdal-dev \
    libgeos-dev \
    libproj-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip wheel --no-cache-dir --wheel-dir /wheels .

FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MAPS4U_DATA_DIR=/var/maps4u \
    MAPS4U_CONFIG_DIR=/app/config \
    MAPS4U_SCHEMA_DIR=/app/schemas \
    MAPS4U_STYLE_DIR=/app/styles

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    fonts-dejavu-core \
    gdal-bin \
    libgeos-c1v5 \
    libproj25 \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir /wheels/*.whl && rm -rf /wheels

COPY config ./config
COPY schemas ./schemas
COPY styles ./styles
COPY scripts ./scripts
COPY docs ./docs

RUN mkdir -p /var/maps4u
EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/healthz || exit 1

CMD ["uvicorn", "maps4u.api.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
