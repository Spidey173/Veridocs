# Production Multi-Stage Dockerfile for Veridocs Backend & Worker
FROM python:3.11-slim AS builder

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --prefix=/install -r requirements.txt

# Pre-download the Fastembed embedding model during build stage
ENV PYTHONPATH="/install/lib/python3.11/site-packages"
RUN python -c "from fastembed import TextEmbedding; TextEmbedding('BAAI/bge-small-en-v1.5')"

# Final runtime image (shared by API and Worker)
FROM python:3.11-slim AS runtime

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/install/bin:$PATH" \
    PYTHONPATH="/app:/app/backend:/install/lib/python3.11/site-packages" \
    OMP_NUM_THREADS="1" \
    MKL_NUM_THREADS="1" \
    OPENBLAS_NUM_THREADS="1" \
    ONNXRUNTIME_INTER_OP_NUM_THREADS="1" \
    ONNXRUNTIME_INTRA_OP_NUM_THREADS="1"

# Install runtime system dependencies for Tesseract OCR, PDF parsing, Office conversion, and healthchecks
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libpq5 \
    tesseract-ocr \
    tesseract-ocr-eng \
    libgl1 \
    libglib2.0-0 \
    libreoffice-writer \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /install /install
COPY --from=builder /root/.cache /root/.cache
COPY public/ /app/public/
COPY backend/ /app/backend/

# Mirror backend modules at /app root for direct entrypoint execution
RUN cp -r /app/backend/* /app/ && mkdir -p /app/data /app/uploads

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

# Default command runs FastAPI server; worker service overrides with worker command
CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
