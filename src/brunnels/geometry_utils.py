#!/usr/bin/env python3
"""
Geometry and distance calculation utilities for route analysis.
"""

from typing import NamedTuple
import logging
import math

logger = logging.getLogger(__name__)


class Position(NamedTuple):
    latitude: float
    longitude: float


def bearings_aligned(
    bearing1: float, bearing2: float, tolerance_degrees: float
) -> bool:
    """
    Check if two bearings are aligned within tolerance (same direction or opposite direction).

    Args:
        bearing1: First bearing in degrees (0-360)
        bearing2: Second bearing in degrees (0-360)
        tolerance_degrees: Allowed deviation in degrees

    Returns:
        True if bearings are aligned within tolerance, False otherwise
    """
    # Calculate difference and normalize to 0-180 range
    diff = abs(bearing1 - bearing2)
    diff = min(diff, 360 - diff)  # Handle wraparound (e.g., 10° and 350°)

    # Check if aligned in same direction or opposite direction
    same_direction = diff <= tolerance_degrees
    opposite_direction = abs(diff - 180) <= tolerance_degrees

    return same_direction or opposite_direction


def bearing(start, end: "Position") -> float:
    if start == end:
        return 0.0
    if math.isclose(start.latitude, 90.0):
        return 180.0
    if math.isclose(start.latitude, -90.0):
        return 0.0
    if math.isclose(end.latitude, 90.0):
        return 0.0
    if math.isclose(end.latitude, -90.0):
        return 180.0
    lat1 = math.radians(start.latitude)
    lat2 = math.radians(end.latitude)
    lon1 = math.radians(start.longitude)
    lon2 = math.radians(end.longitude)
    delta_lon = lon2 - lon1
    y = math.sin(delta_lon) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(
        delta_lon
    )
    bearing = math.atan2(y, x)
    bearing = math.degrees(bearing)
    bearing = (bearing + 360) % 360
    return bearing
