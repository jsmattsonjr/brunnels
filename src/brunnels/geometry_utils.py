#!/usr/bin/env python3
"""
Geometry and distance calculation utilities for route analysis.
"""

from typing import List, Tuple, Optional
import math
import logging
from geopy.distance import geodesic

from .geometry import Position

logger = logging.getLogger(__name__)


def haversine_distance(pos1: Position, pos2: Position) -> float:
    """
    Calculate the geodesic distance between two positions using geopy.

    Args:
        pos1: First position
        pos2: Second position

    Returns:
        Distance in kilometers
    """
    return geodesic(
        (pos1.latitude, pos1.longitude), (pos2.latitude, pos2.longitude)
    ).kilometers


def calculate_cumulative_distances(route: List[Position]) -> List[float]:
    """
    Calculate cumulative distances along a route.

    Args:
        route: List of Position objects representing the route

    Returns:
        List of cumulative distances in kilometers, with same length as route
    """
    if not route:
        return []

    cumulative_distances = [0.0]  # Start at 0

    for i in range(1, len(route)):
        segment_distance = haversine_distance(route[i - 1], route[i])
        cumulative_distances.append(cumulative_distances[-1] + segment_distance)

    return cumulative_distances


def point_to_line_segment_distance_and_projection(
    point: Position, seg_start: Position, seg_end: Position
) -> Tuple[float, float, Position]:
    """
    Calculate the distance from a point to a line segment and find the closest point on the segment.

    Args:
        point: Point to measure distance from
        seg_start: Start of line segment
        seg_end: End of line segment

    Returns:
        Tuple of (distance_km, parameter_t, closest_point) where:
        - distance_km: Shortest distance from point to segment in km
        - parameter_t: Parameter (0-1) indicating position along segment (0=start, 1=end)
        - closest_point: Position of closest point on the segment
    """
    # Convert to radians for calculation
    lat_p, lon_p = math.radians(point.latitude), math.radians(point.longitude)
    lat_a, lon_a = math.radians(seg_start.latitude), math.radians(seg_start.longitude)
    lat_b, lon_b = math.radians(seg_end.latitude), math.radians(seg_end.longitude)

    # For small distances, we can approximate using projected coordinates
    # This is much simpler than spherical geometry and adequate for local calculations

    # Project to approximate Cartesian coordinates (meters)
    earth_radius = 6371000  # meters
    cos_lat_avg = math.cos((lat_a + lat_b) / 2)

    # Convert to meters from start point
    x_p = (lon_p - lon_a) * earth_radius * cos_lat_avg
    y_p = (lat_p - lat_a) * earth_radius

    x_a = 0.0
    y_a = 0.0

    x_b = (lon_b - lon_a) * earth_radius * cos_lat_avg
    y_b = (lat_b - lat_a) * earth_radius

    # Vector from A to B
    dx = x_b - x_a
    dy = y_b - y_a

    # Handle degenerate case where segment has zero length
    if dx == 0 and dy == 0:
        distance_m = math.sqrt(x_p**2 + y_p**2)
        return distance_m / 1000.0, 0.0, seg_start

    # Project point onto line defined by segment
    # t = ((P-A) · (B-A)) / |B-A|²
    t = ((x_p - x_a) * dx + (y_p - y_a) * dy) / (dx**2 + dy**2)

    # Clamp t to [0, 1] to stay within segment
    t = max(0.0, min(1.0, t))

    # Find closest point on segment
    x_closest = x_a + t * dx
    y_closest = y_a + t * dy

    # Calculate distance
    distance_m = math.sqrt((x_p - x_closest) ** 2 + (y_p - y_closest) ** 2)

    # Convert closest point back to lat/lon
    lat_closest = lat_a + (y_closest / earth_radius)
    lon_closest = lon_a + (x_closest / (earth_radius * cos_lat_avg))

    closest_point = Position(
        latitude=math.degrees(lat_closest), longitude=math.degrees(lon_closest)
    )

    return distance_m / 1000.0, t, closest_point


def find_closest_point_on_route(
    point: Position, route: List[Position], cumulative_distances: List[float]
) -> Tuple[float, Position]:
    """
    Find the closest point on a route to a given point and return the cumulative distance.

    Args:
        point: Point to find closest route point for
        route: List of Position objects representing the route
        cumulative_distances: Pre-calculated cumulative distances along route

    Returns:
        Tuple of (cumulative_distance_km, closest_position) where:
        - cumulative_distance_km: Distance from route start to closest point
        - closest_position: Position of closest point on route
    """
    if len(route) < 2:
        if route:
            return 0.0, route[0]
        else:
            raise ValueError("Cannot find closest point on empty route")

    min_distance = float("inf")
    best_cumulative_distance = 0.0
    best_position = route[0]

    # Check each segment of the route
    for i in range(len(route) - 1):
        seg_start = route[i]
        seg_end = route[i + 1]

        distance, t, closest_point = point_to_line_segment_distance_and_projection(
            point, seg_start, seg_end
        )

        if distance < min_distance:
            min_distance = distance
            best_position = closest_point

            # Calculate cumulative distance to this point
            best_cumulative_distance = cumulative_distances[i] + haversine_distance(seg_start, best_position)

    return best_cumulative_distance, best_position


def calculate_bearing(start_pos: Position, end_pos: Position) -> float:
    """
    Calculate the bearing from start_pos to end_pos in degrees (0-360, where 0 is north).

    Args:
        start_pos: Starting position
        end_pos: Ending position

    Returns:
        Bearing in degrees (0-360, where 0° is north, 90° is east)
    """
    lat1 = math.radians(start_pos.latitude)
    lat2 = math.radians(end_pos.latitude)
    lon1 = math.radians(start_pos.longitude)
    lon2 = math.radians(end_pos.longitude)

    dlon = lon2 - lon1

    y = math.sin(dlon) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(
        dlon
    )

    bearing = math.atan2(y, x)
    bearing = math.degrees(bearing)
    bearing = (bearing + 360) % 360  # Normalize to 0-360

    return bearing


def find_closest_segments(
    polyline1: List[Position], polyline2: List[Position]
) -> Tuple[
    Optional[Tuple[int, Position, Position]], Optional[Tuple[int, Position, Position]]
]:
    """
    Find the closest segments between two polylines.

    Args:
        polyline1: First polyline as list of positions
        polyline2: Second polyline as list of positions

    Returns:
        Tuple of (closest_segment1, closest_segment2) where each is:
        (segment_index, segment_start, segment_end) or None if no valid segments found
    """
    if len(polyline1) < 2 or len(polyline2) < 2:
        return None, None

    min_distance = float("inf")
    best_seg1 = None
    best_seg2 = None

    # Check each segment of polyline1 against each segment of polyline2
    for i in range(len(polyline1) - 1):
        seg1_start = polyline1[i]
        seg1_end = polyline1[i + 1]

        for j in range(len(polyline2) - 1):
            seg2_start = polyline2[j]
            seg2_end = polyline2[j + 1]

            # Find closest points between segments
            # Check distance from seg1_start to seg2
            dist1, _, _ = point_to_line_segment_distance_and_projection(
                seg1_start, seg2_start, seg2_end
            )
            # Check distance from seg1_end to seg2
            dist2, _, _ = point_to_line_segment_distance_and_projection(
                seg1_end, seg2_start, seg2_end
            )
            # Check distance from seg2_start to seg1
            dist3, _, _ = point_to_line_segment_distance_and_projection(
                seg2_start, seg1_start, seg1_end
            )
            # Check distance from seg2_end to seg1
            dist4, _, _ = point_to_line_segment_distance_and_projection(
                seg2_end, seg1_start, seg1_end
            )

            # Use minimum distance between all combinations
            segment_distance = min(dist1, dist2, dist3, dist4)

            if segment_distance < min_distance:
                min_distance = segment_distance
                best_seg1 = (i, seg1_start, seg1_end)
                best_seg2 = (j, seg2_start, seg2_end)

    return best_seg1, best_seg2


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
