"""
Expression Utilities - Apparent (not identity-based) expression analysis.

PRIVACY NOTICE:
- This module analyzes visual facial cues only in an approximate, probabilistic way.
- It does NOT perform face recognition or identity linking.
- It does NOT store face images or biometric data.
- Output is ONLY apparent/observable cues: apparent_smile, neutral, face_not_visible.
- This is NOT a judgment on internal emotions - purely observable visual state.
- Intended for aggregate analytics only (e.g., "30% of interactions showed apparent smile").

Uses basic heuristics based on face detection confidence and region analysis.
For MVP: simple scoring based on detected face region brightness and proportion.
TODO: Integrate lightweight smile detector (e.g. haarcascade_smile) if needed.
"""
import cv2
import numpy as np
from typing import Optional, Tuple


EXPRESSION_LABELS = ["apparent_smile", "neutral", "face_not_visible"]


def analyze_apparent_expression(
    frame: np.ndarray,
    bbox: Tuple[int, int, int, int],
    face_detector=None
) -> str:
    """
    Analyze apparent facial expression in a bounding box region.
    
    Privacy-safe: Returns one of three states only:
    - 'apparent_smile'     : face detected, upward mouth curve visible
    - 'neutral'            : face detected, no clear smile cue
    - 'face_not_visible'   : face not detected or too small/occluded
    
    Args:
        frame: Full video frame (BGR)
        bbox: Person bounding box (x1, y1, x2, y2)
        face_detector: Optional pre-loaded haarcascade face detector
    Returns:
        Expression label string
    """
    try:
        x1, y1, x2, y2 = [int(v) for v in bbox]
        # Crop to upper ~40% of body (head region)
        head_y2 = y1 + int((y2 - y1) * 0.4)
        head_region = frame[max(0, y1):head_y2, max(0, x1):x2]

        if head_region.size == 0 or head_region.shape[0] < 20 or head_region.shape[1] < 20:
            return "face_not_visible"

        # Use haarcascade if available
        if face_detector is not None:
            gray = cv2.cvtColor(head_region, cv2.COLOR_BGR2GRAY)
            faces = face_detector.detectMultiScale(
                gray, scaleFactor=1.1, minNeighbors=3, minSize=(20, 20)
            )
            if len(faces) == 0:
                return "face_not_visible"

            # Try smile detection in detected face region
            for (fx, fy, fw, fh) in faces:
                face_roi = gray[fy:fy+fh, fx:fx+fw]
                # Simple brightness ratio heuristic for lower face
                lower_face = face_roi[int(fh*0.5):, :]
                upper_face = face_roi[:int(fh*0.5), :]
                if lower_face.size > 0 and upper_face.size > 0:
                    lower_mean = np.mean(lower_face)
                    upper_mean = np.mean(upper_face)
                    # Heuristic: smile often brightens lower face slightly
                    if lower_mean > upper_mean * 1.05:
                        return "apparent_smile"
                return "neutral"

        # Fallback: face not detectable without dedicated detector
        return "face_not_visible"

    except Exception:
        return "face_not_visible"


def load_face_detector():
    """
    Load OpenCV haarcascade face detector.
    Returns None if unavailable (graceful degradation).
    """
    try:
        detector = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        )
        if detector.empty():
            return None
        return detector
    except Exception:
        return None
