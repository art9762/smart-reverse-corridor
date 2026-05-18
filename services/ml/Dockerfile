FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    YOLO_CONFIG_DIR=/tmp/Ultralytics

# OpenCV runtime deps (libgl, libglib) + ffmpeg for RTSP/MP4 decoding
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 \
        libglib2.0-0 \
        ffmpeg \
        ca-certificates \
        wget \
    && rm -rf /var/lib/apt/lists/*

# Non-root user
RUN useradd -m -u 1000 mluser

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download YOLOv8n weights to /models so first run doesn't hit network.
RUN mkdir -p /models && \
    python -c "from ultralytics import YOLO; YOLO('yolov8n.pt')" && \
    cp -f /root/.config/Ultralytics/yolov8n.pt /models/yolov8n.pt 2>/dev/null || true && \
    cp -f yolov8n.pt /models/yolov8n.pt 2>/dev/null || true && \
    ls -la /models || true

COPY app/ ./app/

RUN mkdir -p /data && chown -R mluser:mluser /app /models /data /tmp

USER mluser

ENV ML_MODEL=/models/yolov8n.pt

CMD ["python", "-m", "app.main"]
