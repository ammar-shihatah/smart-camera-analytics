"""
RTSP → MJPEG Stream Manager
Converts RTSP camera streams into browser-compatible MJPEG multipart streams.
The browser displays them via a plain <img> tag — no plugins needed.
"""
import asyncio
import logging
import time
from typing import Optional, AsyncGenerator

import cv2
import numpy as np

logger = logging.getLogger(__name__)

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
    Inject username:password into RTSP URL if not already present.
    rtsp://ip:port/path  →  rtsp://user:pass@ip:port/path
    """
    if not stream_url:
        return ""
    if username and password:
        if "://" in stream_url:
            proto, rest = stream_url.split("://", 1)
            if "@" not in rest:
                stream_url = f"{proto}://{username}:{password}@{rest}"
    return stream_url


# ─── Sync RTSP test (runs in thread executor) ─────────────────────────────────

def test_rtsp_sync(url: str) -> dict:
    """
    Try to open the RTSP stream and read one frame.
    Returns a detailed diagnostic dict.
    """
    t0 = time.time()
    cap = None
    try:
        cap = cv2.VideoCapture(url)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 8000)
        cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, 6000)

        if not cap.isOpened():
            return {
                "success": False,
                "connection_status": "unreachable",
                "rtsp_reachable": False,
                "backend_can_open_stream": False,
                "error_message": "Cannot open RTSP stream",
                "suggested_fix": (
                    "1) Confirm camera IP is reachable from the server  "
                    "2) Check RTSP port (default 554)  "
                    "3) Verify URL format: rtsp://ip:port/path"
                ),
            }

        ret, frame = cap.read()
        elapsed_ms = int((time.time() - t0) * 1000)

        if not ret or frame is None:
            return {
                "success": False,
                "connection_status": "connected_no_frames",
                "rtsp_reachable": True,
                "backend_can_open_stream": False,
                "error_message": "Connected but cannot read frames",
                "suggested_fix": (
                    "Check camera username/password and RTSP stream path. "
                    "Some cameras require the full channel path."
                ),
            }

        h, w = frame.shape[:2]
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
        return {
            "success": False,
            "connection_status": "error",
            "rtsp_reachable": False,
            "backend_can_open_stream": False,
            "error_message": str(exc),
            "suggested_fix": "Check RTSP URL syntax and network connectivity",
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
) -> AsyncGenerator[bytes, None]:
    """
    Async generator that yields MJPEG multipart frames.
    Usage: StreamingResponse(mjpeg_generator(...), media_type="multipart/x-mixed-replace; boundary=frame")
    """
    BOUNDARY = b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
    frame_delay = 1.0 / max(1, min(fps, 30))
    loop = asyncio.get_event_loop()

    url = build_rtsp_url(stream_url, username, password)

    # ── No URL configured ────────────────────────────────
    if not url:
        placeholder = _make_placeholder("No Stream URL", "Add an RTSP URL in camera settings")
        while True:
            yield BOUNDARY + placeholder + b"\r\n"
            await asyncio.sleep(2)
        return

    # ── Open capture in thread ────────────────────────────
    def _open():
        c = cv2.VideoCapture(url)
        c.set(cv2.CAP_PROP_BUFFERSIZE, 2)
        c.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 8000)
        c.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, 5000)
        return c

    logger.info(f"Opening RTSP stream: {url[:40]}...")
    cap = await loop.run_in_executor(None, _open)

    if not cap.isOpened():
        logger.warning(f"Cannot open stream: {url[:40]}")
        placeholder = _make_placeholder(
            "Cannot Connect to Camera",
            f"URL: {url[:50]}  |  Check IP, port, and credentials"
        )
        while True:
            yield BOUNDARY + placeholder + b"\r\n"
            await asyncio.sleep(3)
        return

    logger.info(f"Stream opened successfully: {url[:40]}")
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
                    cap = await loop.run_in_executor(None, _open)
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
        logger.info(f"Stream closed: {url[:40]}")
