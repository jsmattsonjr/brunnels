#!/usr/bin/env python3
"""
Distance calculation utilities for route analysis.
"""

from typing import List, Tuple
import math
import logging
from models import Position

logger = logging.getLogger(__name__)


def haversine_distance(pos1: Position, pos2: Position) -> float:
    """
    Calculate the haversine distance between two positions.
    
    Args:
        pos1: First position
        pos2: Second position
        
    Returns:
        Distance in kilometers
    """
    # Convert latitude and longitude from degrees to radians
    lat1, lon1 = math.radians(pos1.latitude), math.radians(pos1.longitude)
    lat2, lon2 = math.radians(pos2.latitude), math.radians(pos2.longitude)
    
    # Haversine formula
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    c = 2 * math.asin(math.sqrt(a))
    
    # Radius of earth in kilometers
    r = 6371
    
    return c * r


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
        segment_distance = haversine_distance(route[i-1], route[i])
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
    distance_m = math.sqrt((x_p - x_closest)**2 + (y_p - y_closest)**2)
    
    # Convert closest point back to lat/lon
    lat_closest = lat_a + (y_closest / earth_radius)
    lon_closest = lon_a + (x_closest / (earth_radius * cos_lat_avg))
    
    closest_point = Position(
        latitude=math.degrees(lat_closest),
        longitude=math.degrees(lon_closest)
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
    
    min_distance = float('inf')
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
            segment_length = cumulative_distances[i + 1] - cumulative_distances[i]
            best_cumulative_distance = cumulative_distances[i] + t * segment_length
    
    return best_cumulative_distance, best_position
