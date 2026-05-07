# ── Build Stage ───────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /app

# Install deps first (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

# ── Runtime Stage ─────────────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy source code
COPY main.py .

# Railway injects $PORT at runtime — Gradio needs this env var too
ENV GRADIO_SERVER_NAME=0.0.0.0

# Expose default port (Railway overrides with $PORT)
EXPOSE 7860

CMD ["python", "main.py"]
