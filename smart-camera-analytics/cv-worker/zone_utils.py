"""
Zone Utilities - Geometry helpers for zone-based analytics.

Handles:
- point_in_polygon: Ray casting algorithm
- get_zone_for_point: Finds which zone a centroid belongs to
- calculate_dwell_time_per_zone: Accumulates dwell time per person/zone
"""
from typing import Optional, List, Tuple, Dict


def point_in_polygon(point: Tuple[float, float], polygon: List[List[float]]) -> bool:
    """
    Ray casting algorithm to determine if a point is inside a polygon.
    
    Args:
        point: (x, y) coordinate
        polygon: List of [x, y] vertices
    Returns:
        True if point is inside polygon
    """
    if len(polygon) < 3:
        return False

    x, y = point
    n = len(polygon)
    inside = False

    j = n - 1
    for i in range(n):
        xi, yi = polygon[i][0], polygon[i][1]
        xj, yj = polygon[j][0], polygon[j][1]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi + 1e-10) + xi):
            inside = not inside
        j = i

    return inside


def get_zone_for_point(
    point: Tuple[float, float],
    zones: List[Dict]
) -> Optional[Dict]:
    """
    Find which zone a point belongs to.
    If multiple zones overlap, returns the first match (priority by order).
    
    Args:
        point: (x, y) centroid
        zones: List of zone dicts with keys: id, name, type, polygon_json
    Returns:
        Zone dict or None
    """
    for zone in zones:
        polygon = zone.get("polygon_json") or zone.get("polygon", [])
        if polygon and point_in_polygon(point, polygon):
            return zone
    return None


def calculate_movement_score(
    centroid_history: List[Tuple[float, float]],
    frame_width: int = 640,
    frame_height: int = 480
) -> float:
    """
    Calculate movement score based on centroid displacement history.
    Normalized to 0-1 range relative to frame size.
    
    Args:
        centroid_history: List of (x, y) centroids in order
        frame_width: Frame width for normalization
        frame_height: Frame height for normalization
    Returns:
        Movement score 0.0 (stationary) to 1.0 (high movement)
    """
    if len(centroid_history) < 2:
        return 0.0

    total_dist = 0.0
    for i in range(1, len(centroid_history)):
        dx = centroid_history[i][0] - centroid_history[i-1][0]
        dy = centroid_history[i][1] - centroid_history[i-1][1]
        total_dist += (dx**2 + dy**2) ** 0.5

    # Normalize by diagonal
    diagonal = (frame_width**2 + frame_height**2) ** 0.5
    score = min(total_dist / (diagonal * max(len(centroid_history), 1)), 1.0)
    return round(score, 4)


def get_centroid(bbox: List[float]) -> Tuple[float, float]:
    """
    Calculate centroid from bounding box [x1, y1, x2, y2].
    """
    x1, y1, x2, y2 = bbox
    return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)
