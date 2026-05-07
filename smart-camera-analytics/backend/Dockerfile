FROM python:3.11-slim

WORKDIR /app

# System libs required by opencv-python-headless + ffmpeg
RUN apt-get update && apt-get install -y --no-install-recommends \
    # OpenCV core dependencies
    libglib2.0-0 \
    libgomp1 \
    libgl1 \
    libglib2.0-dev \
    # Required for OpenCV video / image codecs
    libsm6 \
    libxext6 \
    libxrender1 \
    libfontconfig1 \
    # FFmpeg for RTSP support inside OpenCV
    ffmpeg \
    libavcodec-dev \
    libavformat-dev \
    libswscale-dev \
    # Networking tools (handy for debugging inside container)
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# Upgrade pip first, then install deps
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Verify OpenCV loaded correctly — build fails fast if something is wrong
RUN python -c "import cv2; print('✅ OpenCV', cv2.__version__, 'loaded OK')"

COPY . .

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
