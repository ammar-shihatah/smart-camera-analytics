FROM python:3.11-slim

# Install system dependencies for OpenCV + FFmpeg
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt requirements-yolo.txt ./
RUN pip install --no-cache-dir -r requirements.txt

ARG INSTALL_YOLO=false
RUN if [ "$INSTALL_YOLO" = "true" ]; then \
      pip install --no-cache-dir -r requirements-yolo.txt && \
      python -c "from ultralytics import YOLO; YOLO('yolov8n.pt')" ; \
    else \
      echo "Skipping YOLO install. Set INSTALL_YOLO=true for YOLOv8 detection."; \
    fi

COPY . .

CMD ["python", "worker.py", "--auto-cameras", "--no-preview"]
