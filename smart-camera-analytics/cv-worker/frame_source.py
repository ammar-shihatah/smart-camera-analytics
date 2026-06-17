"""
Frame source abstraction for analysis workers.

RTSP streams are read through FFmpeg image pipes because many DVR/NVR streams
are less stable through cv2.VideoCapture. Local files/webcams still use OpenCV.
"""
import logging
import os
import select
import subprocess
import time
from typing import Optional
from urllib.parse import urlsplit, urlunsplit

import cv2
import numpy as np

logger = logging.getLogger(__name__)


_LOCAL_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0"}


def _rtsp_transport() -> str:
    value = os.getenv("RTSP_TRANSPORT", "tcp").lower()
    return value if value in {"tcp", "udp"} else "tcp"


def build_stream_url(stream_url: str, username: Optional[str] = None, password: Optional[str] = None) -> str:
    if not stream_url:
        return ""

    url = stream_url.strip()
    if username and password and "://" in url:
        proto, rest = url.split("://", 1)
        if "@" not in rest.split("/", 1)[0]:
            url = f"{proto}://{username}:{password}@{rest}"

    try:
        parts = urlsplit(url)
        if parts.hostname and parts.hostname.lower() in _LOCAL_HOSTS:
            userinfo = ""
            if parts.username:
                userinfo = parts.username
                if parts.password:
                    userinfo += f":{parts.password}"
                userinfo += "@"
            port = f":{parts.port}" if parts.port else ""
            url = urlunsplit((parts.scheme, f"{userinfo}host.docker.internal{port}", parts.path, parts.query, parts.fragment))
    except Exception:
        pass

    return url


def _is_bad_frame(frame: np.ndarray) -> bool:
    if frame is None:
        return True
    h, w = frame.shape[:2]
    if h < 20 or w < 20:
        return True
    mean_b, mean_g, mean_r = frame.mean(axis=(0, 1))
    return mean_g > 70 and mean_r < 40 and mean_b < 40


class FrameSource:
    def __init__(self, source, username: Optional[str] = None, password: Optional[str] = None, fps: int = 5):
        self.source = source
        self.username = username
        self.password = password
        self.fps = max(1, min(int(fps or 5), 15))
        self.cap = None
        self.proc = None
        self.buf = b""
        self.frame_shape = None
        self.use_ffmpeg = isinstance(source, str) and source.lower().startswith("rtsp://")

    def open(self) -> bool:
        if self.use_ffmpeg:
            return self._open_ffmpeg()
        self.cap = cv2.VideoCapture(self.source)
        return self.cap.isOpened()

    def _open_ffmpeg(self) -> bool:
        url = build_stream_url(self.source, self.username, self.password)
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel", "error",
            "-rtsp_transport", _rtsp_transport(),
            "-fflags", "+discardcorrupt",
            "-err_detect", "ignore_err",
            "-flags", "low_delay",
            "-analyzeduration", os.getenv("FFMPEG_ANALYZEDURATION_US", "2000000"),
            "-probesize", os.getenv("FFMPEG_PROBESIZE", "1000000"),
            "-i", url,
            "-an",
            "-vf", f"fps={self.fps}",
            "-q:v", "5",
            "-f", "image2pipe",
            "-vcodec", "mjpeg",
            "pipe:1",
        ]
        logger.info("Opening RTSP analysis stream with FFmpeg")
        self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        return self.proc.poll() is None

    def read(self):
        if self.use_ffmpeg:
            return self._read_ffmpeg()
        return self.cap.read()

    def _read_ffmpeg(self):
        if not self.proc or self.proc.poll() is not None:
            self.release()
            if not self._open_ffmpeg():
                time.sleep(2)
                return False, None

        deadline = time.time() + 10
        fd = self.proc.stdout.fileno()
        while time.time() < deadline:
            readable, _, _ = select.select([fd], [], [], max(0.1, deadline - time.time()))
            if not readable:
                break

            chunk = os.read(fd, 4096)
            if not chunk:
                self.release()
                return False, None
            self.buf += chunk

            while True:
                start = self.buf.find(b"\xff\xd8")
                end = self.buf.find(b"\xff\xd9", start + 2) if start != -1 else -1
                if start == -1:
                    self.buf = self.buf[-2:]
                    break
                if end == -1:
                    if start > 0:
                        self.buf = self.buf[start:]
                    break

                jpeg = self.buf[start:end + 2]
                self.buf = self.buf[end + 2:]
                frame = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
                if _is_bad_frame(frame):
                    continue
                self.frame_shape = frame.shape
                return True, frame

        return False, None

    def get(self, prop):
        if self.cap:
            return self.cap.get(prop)
        if self.frame_shape is None:
            return 0
        h, w = self.frame_shape[:2]
        if prop == cv2.CAP_PROP_FRAME_WIDTH:
            return w
        if prop == cv2.CAP_PROP_FRAME_HEIGHT:
            return h
        if prop == cv2.CAP_PROP_FPS:
            return self.fps
        return 0

    def set(self, prop, value):
        if self.cap:
            return self.cap.set(prop, value)
        return False

    def release(self):
        if self.cap:
            self.cap.release()
            self.cap = None
        if self.proc:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.proc.kill()
            self.proc = None


