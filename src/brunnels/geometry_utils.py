#!/usr/bin/env python3
"""
Geometry and distance calculation utilities for route analysis.
"""

from typing import List, Tuple, Optional
from dataclasses import dataclass, field
from geopy.distance import geodesic
from shapely.geometry import LineString, Point
from shapely.ops import nearest_points
import math
import logging

from .shapely_utils import linestring_distance_to_index

logger = logging.getLogger(__name__)


def find_closest_segments(
    linestring1: LineString, linestring2: LineString
) -> Tuple[int, int]:
    """
    Find the closest segments between two linestrings.

    Args:
        linestring1: First linestring
        linestring2: Second linestring

    Returns:
        Tuple of (closest_segment1, closest_segment2)
    """
    point1, point2 = nearest_points(linestring1, linestring2)
    distance1 = linestring1.project(point1)
    distance2 = linestring2.project(point2)
    segment1 = linestring_distance_to_index(linestring1, distance1)
    segment2 = linestring_distance_to_index(linestring2, distance2)
    return (segment1, segment2)


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


@dataclass
class Position:
    latitude: float
    longitude: float
    elevation: Optional[float] = None

    def has_elevation(self) -> bool:
        return self.elevation is not None

    def distance_to(self, other: "Position") -> float:
        return geodesic(
            (self.latitude, self.longitude), (other.latitude, other.longitude)
        ).kilometers

    def bearing_to(self, other: "Position") -> float:
        if self == other:
            return 0.0
        if math.isclose(self.latitude, 90.0):
            return 180.0
        if math.isclose(self.latitude, -90.0):
            return 0.0
        if math.isclose(other.latitude, 90.0):
            return 0.0
        if math.isclose(other.latitude, -90.0):
            return 180.0
        lat1 = math.radians(self.latitude)
        lat2 = math.radians(other.latitude)
        lon1 = math.radians(self.longitude)
        lon2 = math.radians(other.longitude)
        dlon = lon2 - lon1
        y = math.sin(dlon) * math.cos(lat2)
        x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(
            lat2
        ) * math.cos(dlon)
        bearing = math.atan2(y, x)
        bearing = math.degrees(bearing)
        bearing = (bearing + 360) % 360
        return bearing

    def to_line_segment_distance_and_projection(
        self, seg_start: "Position", seg_end: "Position"
    ) -> Tuple[float, float, "Position"]:
        lat_p, lon_p = math.radians(self.latitude), math.radians(self.longitude)
        lat_a, lon_a = math.radians(seg_start.latitude), math.radians(
            seg_start.longitude
        )
        lat_b, lon_b = math.radians(seg_end.latitude), math.radians(seg_end.longitude)
        earth_radius = 6371000
        cos_lat_avg = math.cos((lat_a + lat_b) / 2)
        x_p = (lon_p - lon_a) * earth_radius * cos_lat_avg
        y_p = (lat_p - lat_a) * earth_radius
        x_a = 0.0
        y_a = 0.0
        x_b = (lon_b - lon_a) * earth_radius * cos_lat_avg
        y_b = (lat_b - lat_a) * earth_radius
        dx = x_b - x_a
        dy = y_b - y_a
        if dx == 0 and dy == 0:
            distance_m = math.sqrt(x_p**2 + y_p**2)
            return distance_m / 1000.0, 0.0, seg_start
        t = ((x_p - x_a) * dx + (y_p - y_a) * dy) / (dx**2 + dy**2)
        t = max(0.0, min(1.0, t))
        x_closest = x_a + t * dx
        y_closest = y_a + t * dy
        distance_m = math.sqrt((x_p - x_closest) ** 2 + (y_p - y_closest) ** 2)
        lat_closest = lat_a + (y_closest / earth_radius)
        lon_closest = lon_a + (x_closest / (earth_radius * cos_lat_avg))
        closest_point = Position(
            latitude=math.degrees(lat_closest), longitude=math.degrees(lon_closest)
        )
        return distance_m / 1000.0, t, closest_point
