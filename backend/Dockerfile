# ============================================================
# Stage 1: Builder — install Python dependencies
# ============================================================
FROM python:3.12-slim AS builder

WORKDIR /build

# Install build tools for native extensions (scipy/numpy)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ============================================================
# Stage 2: Runtime — minimal image
# ============================================================
FROM python:3.12-slim AS runtime

WORKDIR /app

# Non-root user for security
RUN groupadd --system appgroup && useradd --system --gid appgroup appuser

# Copy installed packages from builder (world-readable location)
COPY --from=builder /install /usr/local

# Copy application source
COPY . .

ENV PATH=/usr/local/bin:$PATH
ENV PYTHONPATH=/app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV CORS_ORIGINS=http://localhost:3000,http://localhost:5173

# Switch to non-root
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
