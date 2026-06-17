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

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Pre-download YOLOv8 nano weights
RUN python -c "from ultralytics import YOLO; YOLO('yolov8n.pt')" || true

CMD ["python", "worker.py", "--auto-cameras", "--no-preview"]
