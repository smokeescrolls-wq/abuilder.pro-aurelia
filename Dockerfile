FROM python:3.12-slim

# System deps: ffmpeg + libsndfile (for soundfile)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ffmpeg \
        libsndfile1 \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY app/ .

# Create dirs for uploads/outputs
RUN mkdir -p /tmp/aurelia/uploads /tmp/aurelia/outputs

# Non-root user for security
RUN useradd -m -u 1000 aurelia && \
    chown -R aurelia:aurelia /app /tmp/aurelia
USER aurelia

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
