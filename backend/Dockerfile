# Production Dockerfile for Veridocs Backend
FROM python:3.11-slim as builder

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --prefix=/install -r requirements.txt

# Pre-download the Fastembed model during build stage
ENV PYTHONPATH="/install/lib/python3.11/site-packages"
RUN python -c "from fastembed import TextEmbedding; TextEmbedding('BAAI/bge-small-en-v1.5')"

# Final runtime image
FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/install/bin:$PATH" \
    PYTHONPATH="/app:/install/lib/python3.11/site-packages" \
    OMP_NUM_THREADS="1" \
    MKL_NUM_THREADS="1" \
    OPENBLAS_NUM_THREADS="1" \
    ONNXRUNTIME_INTER_OP_NUM_THREADS="1" \
    ONNXRUNTIME_INTRA_OP_NUM_THREADS="1"

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /install /install
COPY --from=builder /root/.cache /root/.cache
COPY . /app

# Ensure data and uploads directories exist with proper permissions
RUN mkdir -p /app/data /app/uploads

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
