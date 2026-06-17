"""
RTSP → MJPEG Stream Manager
Converts RTSP camera streams into browser-compatible MJPEG multipart streams.
The browser displays them via a plain <img> tag — no plugins needed.
"""
import os

# ── Force FFmpeg (used by OpenCV) to talk RTSP over TCP ───────────────────────
# UDP packets are frequently dropped through Docker's bridge/NAT, which is the
# #1 reason "the RTSP camera won't show up". TCP is far more reliable.
# This env var MUST be set before the first cv2.VideoCapture() call.
os.environ.setdefault(
    "OPENCV_FFMPEG_CAPTURE_OPTIONS",
    "rtsp_transport;tcp|stimeout;8000000|max_delay;500000|buffer_size;1048576",
)

import asyncio
import logging
import re
import subprocess
import time
from typing import Optional, AsyncGenerator
from urllib.parse import urlsplit, urlunsplit

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# Hosts that, inside a container, must be rewritten to reach the Docker host.
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0"}


# ─── Placeholder frame generator ──────────────────────────────────────────────

def _make_placeholder(message: str, sub: str = "") -> bytes:
    """Create a dark frame with a text message (returned as JPEG bytes)."""
    img = np.zeros((360, 640, 3), dtype=np.uint8)
    img[:] = (18, 18, 18)

    # Green header bar
    cv2.rectangle(img, (0, 0), (640, 50), (0, 40, 0), -1)
    cv2.putText(img, "SCA SYSTEM", (20, 33),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 200, 80), 2)

    # Camera icon
    cv2.circle(img, (320, 160), 50, (40, 40, 40), -1)
    cv2.circle(img, (320, 160), 35, (30, 30, 30), -1)
    cv2.putText(img, "NO", (298, 153),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (80, 80, 80), 1)
    cv2.putText(img, "SIGNAL", (290, 173),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, (80, 80, 80), 1)

    # Main message
    cv2.putText(img, message, (20, 260),
                cv2.FONT_HERSHEY_SIMPLEX, 0.65, (180, 180, 180), 1)

    # Sub message (error detail)
    if sub:
        words = sub.split()
        lines, cur = [], ""
        for w in words:
            if len(cur + " " + w) > 55:
                lines.append(cur.strip())
                cur = w
            else:
                cur = (cur + " " + w).strip()
        if cur:
            lines.append(cur)
        for i, line in enumerate(lines[:3]):
            cv2.putText(img, line, (20, 295 + i * 22),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.42, (120, 120, 120), 1)

    _, jpeg = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 80])
    return jpeg.tobytes()


# ─── RTSP URL builder ─────────────────────────────────────────────────────────

def build_rtsp_url(stream_url: str, username: Optional[str], password: Optional[str]) -> str:
    """
    Inject username:password into RTSP URL if not already present, and rewrite
    localhost/127.0.0.1 → host.docker.internal so a containerized backend can
    reach a camera/test-server running on the Docker host.

    rtsp://ip:port/path  →  rtsp://user:pass@ip:port/path
    """
    if not stream_url:
        return ""

    url = stream_url.strip()

    # Inject credentials if provided and not already embedded
    if username and password and "://" in url:
        proto, rest = url.split("://", 1)
        if "@" not in rest.split("/", 1)[0]:
            url = f"{proto}://{username}:{password}@{rest}"

    # Rewrite local host so the container can reach the host machine
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
            netloc = f"{userinfo}host.docker.internal{port}"
            url = urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))
    except Exception:
        pass

    return url


def _mask(url: str) -> str:
    """Hide credentials when logging a URL."""
    import re
    return re.sub(r"//[^/@]*@", "//***@", url or "")


def _open_capture(url: str, buffersize: int = 2):
    """Open an RTSP capture using the FFmpeg backend with sane timeouts."""
    cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
    try:
        cap.set(cv2.CAP_PROP_BUFFERSIZE, buffersize)
        # Newer OpenCV builds support these; ignored gracefully otherwise.
        cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 8000)
        cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, 8000)
    except Exception:
        pass
    return cap


def _rtsp_transport(value: str = "tcp") -> str:
    value = (value or "tcp").lower()
    return value if value in {"tcp", "udp"} else "tcp"


def _ffmpeg_cmd(url: str, fps: int = 10) -> list[str]:
    """Build an FFmpeg command that turns RTSP into a stream of JPEG images."""
    fps = max(1, min(int(fps or 10), 15))
    return _ffmpeg_cmd_with_quality(url, fps=fps, jpeg_quality=5)


def _ffmpeg_cmd_with_quality(
    url: str,
    fps: int = 10,
    jpeg_quality: int = 5,
    transport: str = "tcp",
) -> list[str]:
    """Build an FFmpeg command that turns RTSP into JPEG frames."""
    fps = max(1, min(int(fps or 10), 15))
    jpeg_quality = max(2, min(int(jpeg_quality or 5), 31))
    transport = _rtsp_transport(transport)
    return [
        "ffmpeg",
        "-hide_banner",
        "-loglevel", "warning",
        "-rtsp_transport", transport,
        "-fflags", "+discardcorrupt",
        "-err_detect", "ignore_err",
        "-flags", "low_delay",
        "-analyzeduration", os.getenv("FFMPEG_ANALYZEDURATION_US", "2000000"),
        "-probesize", os.getenv("FFMPEG_PROBESIZE", "1000000"),
        "-i", url,
        "-an",
        "-vf", f"fps={fps}",
        "-q:v", str(jpeg_quality),
        "-f", "image2pipe",
        "-vcodec", "mjpeg",
        "pipe:1",
    ]


def apply_stream_profile(url: str, profile: str = "stored") -> str:
    """
    Switch common DVR/NVR channel suffixes without changing the saved camera.

    Hikvision-style RTSP paths use 101 for main/high quality and 102 for
    sub/stable stream. For camera 2 it is usually 201/202, and so on.
    """
    normalized = (profile or "stored").lower()
    if normalized not in {"main", "high", "sub", "stable"}:
        return url

    def repl(match):
        channel = match.group(1)
        if len(channel) < 2:
            return match.group(0)
        suffix = "1" if normalized in {"main", "high"} else "2"
        return f"/Streaming/Channels/{channel[:-1]}{suffix}"

    return re.sub(r"/Streaming/Channels/(\d+)", repl, url, count=1)


def _ffmpeg_one_jpeg_sync(url: str, timeout: float = 20.0) -> Optional[bytes]:
    """
    Ask FFmpeg for one JPEG frame. This is more tolerant than OpenCV for some
    DVR/NVR streams with H.264+/Smart Codec packet quirks.
    """
    proc = subprocess.Popen(
        _ffmpeg_cmd(url, fps=1),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        out, _err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        out, _err = proc.communicate()

    start = out.find(b"\xff\xd8")
    end = out.find(b"\xff\xd9", start + 2)
    if start == -1 or end == -1:
        return None
    jpeg = out[start:end + 2]
    return None if _is_bad_jpeg_frame(jpeg) else jpeg


def _is_bad_jpeg_frame(jpeg: bytes) -> bool:
    """
    Detect decoder-artifact frames. Some DVRs with H.264+/Smart Codec can
    produce a solid green image when FFmpeg gets corrupt packets; showing that
    looks like the app broke, so filter it and show a diagnostic placeholder.
    """
    try:
        img = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            return True
        h, w = img.shape[:2]
        if h < 20 or w < 20:
            return True
        mean_b, mean_g, mean_r = img.mean(axis=(0, 1))
        # Solid green decoder output: B/R are near zero and G dominates. JPEG
        # artifacts may raise std, so key off the channel means instead.
        return mean_g > 70 and mean_r < 40 and mean_b < 40
    except Exception:
        return True


async def _drain_stream(stream: asyncio.StreamReader, label: str):
    """Keep FFmpeg stderr drained so the process cannot block on logs."""
    while True:
        line = await stream.readline()
        if not line:
            break
        text = line.decode(errors="replace").strip()
        if text:
            logger.debug(f"{label}: {text}")


async def _ffmpeg_mjpeg_generator(
    url: str,
    fps: int,
    boundary: bytes,
    jpeg_quality: int = 5,
    transport: str = "tcp",
) -> AsyncGenerator[bytes, None]:
    """
    Stream JPEG frames generated by an FFmpeg subprocess. The stdout is a raw
    sequence of JPEGs, so we split it by JPEG SOI/EOI markers and wrap each
    frame in the multipart boundary expected by browsers.
    """
    placeholder = _make_placeholder("Waiting for FFmpeg", "Decoding RTSP stream...")
    corrupt_placeholder = _make_placeholder(
        "Bad DVR Video Frames",
        "Disable H.265/H.264+/Smart Codec and set I-frame interval = FPS"
    )
    while True:
        proc = await asyncio.create_subprocess_exec(
            *_ffmpeg_cmd_with_quality(url, fps=fps, jpeg_quality=jpeg_quality, transport=transport),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        logger.info(f"FFmpeg stream process started: {_mask(url)}")
        stderr_task = asyncio.create_task(_drain_stream(proc.stderr, "ffmpeg"))
        buf = b""
        yielded = False
        corrupt_frames = 0

        try:
            while True:
                try:
                    chunk = await asyncio.wait_for(proc.stdout.read(8192), timeout=5)
                except asyncio.TimeoutError:
                    if not yielded:
                        yield boundary + placeholder + b"\r\n"
                    continue

                if not chunk:
                    break

                buf += chunk
                while True:
                    start = buf.find(b"\xff\xd8")
                    end = buf.find(b"\xff\xd9", start + 2) if start != -1 else -1
                    if start == -1:
                        buf = buf[-2:]
                        break
                    if end == -1:
                        if start > 0:
                            buf = buf[start:]
                        break
                    jpeg = buf[start:end + 2]
                    buf = buf[end + 2:]
                    if _is_bad_jpeg_frame(jpeg):
                        corrupt_frames += 1
                        if not yielded:
                            yield boundary + corrupt_placeholder + b"\r\n"
                        continue
                    yielded = True
                    yield boundary + jpeg + b"\r\n"
        except asyncio.CancelledError:
            raise
        finally:
            if proc.returncode is None:
                proc.terminate()
                try:
                    await asyncio.wait_for(proc.wait(), timeout=3)
                except asyncio.TimeoutError:
                    proc.kill()
                    await proc.wait()
            stderr_task.cancel()

        logger.warning(f"FFmpeg stream process ended, retrying: {_mask(url)}")
        if not yielded and corrupt_frames:
            yield boundary + corrupt_placeholder + b"\r\n"
        else:
            yield boundary + _make_placeholder("Stream Lost", "Restarting FFmpeg...") + b"\r\n"
        await asyncio.sleep(2)


# ─── Sync RTSP test (runs in thread executor) ─────────────────────────────────

def test_rtsp_sync(url: str) -> dict:
    """
    Try to open the RTSP stream and read one frame.
    Returns a detailed diagnostic dict.
    """
    t0 = time.time()
    cap = None
    logger.info(f"Testing RTSP connection: {_mask(url)}")
    try:
        cap = _open_capture(url, buffersize=1)

        if not cap.isOpened():
            return {
                "success": False,
                "connection_status": "unreachable",
                "rtsp_reachable": False,
                "backend_can_open_stream": False,
                "error_message": "Cannot open RTSP stream (FFmpeg could not connect)",
                "suggested_fix": (
                    "1) Confirm the camera IP is reachable from the SERVER (not just your PC). "
                    "2) Check the RTSP port (default 554). "
                    "3) Verify the URL format: rtsp://ip:port/path. "
                    "4) If the camera is on your PC, use the LAN IP (e.g. 192.168.x.x), not localhost."
                ),
            }

        frame = None
        attempts = 0
        # Some DVRs only deliver a decodable frame after the next keyframe.
        # Wait a little instead of failing on the first corrupt/incomplete packet.
        while time.time() - t0 < 12:
            attempts += 1
            ret, candidate = cap.read()
            if ret and candidate is not None:
                frame = candidate
                break
            time.sleep(0.05)

        elapsed_ms = int((time.time() - t0) * 1000)

        if frame is None:
            ffmpeg_jpeg = _ffmpeg_one_jpeg_sync(url, timeout=22)
            if ffmpeg_jpeg:
                elapsed_ms = int((time.time() - t0) * 1000)
                logger.info(f"RTSP test OK via FFmpeg fallback: {_mask(url)} in {elapsed_ms}ms")
                return {
                    "success": True,
                    "connection_status": "ok_ffmpeg_fallback",
                    "rtsp_reachable": True,
                    "backend_can_open_stream": True,
                    "error_message": None,
                    "suggested_fix": "OpenCV could not decode this DVR stream, but FFmpeg fallback can display it.",
                    "connection_time_ms": elapsed_ms,
                    "resolution": "ffmpeg-decoded",
                }

            return {
                "success": False,
                "connection_status": "connected_no_frames",
                "rtsp_reachable": True,
                "backend_can_open_stream": False,
                "error_message": "Connected to the camera but could not read any video frames",
                "suggested_fix": (
                    "The RTSP port, username, password, and path are reachable, but the video "
                    "payload is not decodable. On the DVR/NVR, set the selected stream to plain "
                    "H.264, disable H.265/H.265+/H.264+/Smart Codec, and set I-frame interval "
                    "close to the FPS value. Then restart the stream and test again."
                ),
                "connection_time_ms": elapsed_ms,
            }

        h, w = frame.shape[:2]
        logger.info(f"RTSP test OK: {_mask(url)} {w}x{h} in {elapsed_ms}ms after {attempts} reads")
        return {
            "success": True,
            "connection_status": "ok",
            "rtsp_reachable": True,
            "backend_can_open_stream": True,
            "error_message": None,
            "suggested_fix": None,
            "connection_time_ms": elapsed_ms,
            "resolution": f"{w}x{h}",
        }

    except Exception as exc:
        logger.error(f"RTSP test error for {_mask(url)}: {exc}")
        return {
            "success": False,
            "connection_status": "error",
            "rtsp_reachable": False,
            "backend_can_open_stream": False,
            "error_message": str(exc),
            "suggested_fix": "Check RTSP URL syntax and network connectivity from the server.",
        }
    finally:
        if cap:
            cap.release()


# ─── Async MJPEG generator ────────────────────────────────────────────────────

async def mjpeg_generator(
    stream_url: str,
    username: Optional[str],
    password: Optional[str],
    fps: int = 15,
    profile: str = "stored",
    jpeg_quality: int = 5,
    transport: str = "tcp",
) -> AsyncGenerator[bytes, None]:
    """
    Async generator that yields MJPEG multipart frames.
    Usage: StreamingResponse(mjpeg_generator(...), media_type="multipart/x-mixed-replace; boundary=frame")
    """
    BOUNDARY = b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
    frame_delay = 1.0 / max(1, min(fps, 30))
    loop = asyncio.get_event_loop()

    url = apply_stream_profile(build_rtsp_url(stream_url, username, password), profile)

    # ── No URL configured ────────────────────────────────
    if not url:
        placeholder = _make_placeholder("No Stream URL", "Add an RTSP URL in camera settings")
        while True:
            yield BOUNDARY + placeholder + b"\r\n"
            await asyncio.sleep(2)
        return

    # RTSP DVR/NVR streams are generally more reliable through the FFmpeg CLI
    # than OpenCV's VideoCapture, especially with H.264+/Smart Codec quirks.
    if url.lower().startswith("rtsp://"):
        async for frame in _ffmpeg_mjpeg_generator(
            url,
            fps,
            BOUNDARY,
            jpeg_quality=jpeg_quality,
            transport=transport,
        ):
            yield frame
        return

    # ── Open capture in thread ────────────────────────────
    logger.info(f"Opening RTSP stream: {_mask(url)}")
    cap = await loop.run_in_executor(None, _open_capture, url)

    if not cap.isOpened():
        logger.warning(f"Cannot open stream: {_mask(url)}")
        placeholder = _make_placeholder(
            "Cannot Connect to Camera",
            f"{_mask(url)}  |  Check IP, port, credentials, and that the server can reach the camera"
        )
        try:
            while True:
                yield BOUNDARY + placeholder + b"\r\n"
                await asyncio.sleep(3)
        finally:
            cap.release()
        return

    logger.info(f"Stream opened successfully: {_mask(url)}")
    failures = 0
    reconnect_after = 8

    try:
        while True:
            ret, frame = await loop.run_in_executor(None, cap.read)

            if not ret or frame is None:
                failures += 1
                logger.debug(f"Frame read failed ({failures}/{reconnect_after})")

                if failures >= reconnect_after:
                    placeholder = _make_placeholder("Stream Lost", "Reconnecting…")
                    yield BOUNDARY + placeholder + b"\r\n"
                    await asyncio.sleep(2)
                    cap.release()
                    cap = await loop.run_in_executor(None, _open_capture, url)
                    failures = 0
                    if not cap.isOpened():
                        placeholder = _make_placeholder("Reconnect Failed", "Retrying in 5s…")
                        yield BOUNDARY + placeholder + b"\r\n"
                        await asyncio.sleep(5)
                continue

            failures = 0

            # Encode to JPEG
            encode_params = [cv2.IMWRITE_JPEG_QUALITY, 75]
            ret_enc, jpeg = await loop.run_in_executor(
                None, lambda: cv2.imencode(".jpg", frame, encode_params)
            )
            if ret_enc:
                yield BOUNDARY + jpeg.tobytes() + b"\r\n"

            await asyncio.sleep(frame_delay)

    except asyncio.CancelledError:
        logger.info("Stream generator cancelled (client disconnected)")
    except Exception as exc:
        logger.error(f"Stream error: {exc}")
        placeholder = _make_placeholder("Stream Error", str(exc)[:80])
        yield BOUNDARY + placeholder + b"\r\n"
    finally:
        if cap:
            cap.release()
        logger.info(f"Stream closed: {_mask(url)}")
