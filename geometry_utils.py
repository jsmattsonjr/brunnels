#!/usr/bin/env python3
"""
Updated geometry_utils.py functions to handle compound brunnels.
This shows the updated functions that need to be added/modified in geometry_utils.py
"""

from typing import List, Optional, Union
import logging
from math import cos, radians
from shapely.geometry import LineString
from geometry import Position, Geometry
from brunnel_way import BrunnelWay, FilterReason, RouteSpan
from route import Route
from distance_utils import (
    calculate_cumulative_distances,
    find_closest_point_on_route,
    find_closest_segments,
    calculate_bearing,
    bearings_aligned,
    haversine_distance,
)

logger = logging.getLogger(__name__)

# Import compound brunnel way with fallback for backwards compatibility
try:
    from compound_brunnel_way import CompoundBrunnelWay

    BrunnelLike = Union[BrunnelWay, CompoundBrunnelWay]
except ImportError:
    CompoundBrunnelWay = None
    BrunnelLike = BrunnelWay


def positions_to_linestring(positions: List[Position]) -> Optional[LineString]:
    """
    Convert a list of Position objects to a Shapely LineString.

    Note: This function now delegates to the Geometry base class method.

    Args:
        positions: List of Position objects

    Returns:
        LineString object, or None if positions is empty or has less than 2 points
    """
    return Geometry._positions_to_linestring(positions)


def calculate_brunnel_route_span(
    brunnel: BrunnelWay, route: Route, cumulative_distances: List[float]
) -> RouteSpan:
    """
    Calculate the span of a brunnel along the route.

    Args:
        brunnel: BrunnelWay object to calculate span for
        route: Route object representing the route
        cumulative_distances: Pre-calculated cumulative distances along route

    Returns:
        RouteSpan object with start/end distances and length
    """
    if not brunnel.coords:
        return RouteSpan(0.0, 0.0, 0.0)

    min_distance = float("inf")
    max_distance = -float("inf")

    # Find the closest route point for each brunnel coordinate
    for brunnel_point in brunnel.coords:
        cumulative_dist, _ = find_closest_point_on_route(
            brunnel_point, route.positions, cumulative_distances
        )

        min_distance = min(min_distance, cumulative_dist)
        max_distance = max(max_distance, cumulative_dist)

    return RouteSpan(min_distance, max_distance, max_distance - min_distance)


def route_contains_brunnel(route_geometry, brunnel: BrunnelWay) -> bool:
    """
    Check if a route geometry completely contains a brunnel (bridge or tunnel).

    Args:
        route_geometry: Shapely geometry object representing the buffered route polygon
        brunnel: BrunnelWay object to check for containment

    Returns:
        True if the route geometry completely contains the brunnel, False otherwise
    """
    try:
        # Get cached LineString from brunnel
        brunnel_line = brunnel.get_linestring()
        if brunnel_line is None:
            return False

        # Check if route geometry completely contains the brunnel
        return route_geometry.contains(brunnel_line)

    except Exception as e:
        logger.warning(
            f"Failed to check containment for brunnel {brunnel.metadata.get('id', 'unknown')}: {e}"
        )
        return False


def check_bearing_alignment(
    brunnel: BrunnelWay, route: Route, tolerance_degrees: float
) -> bool:
    """
    Check if a brunnel's bearing is aligned with the route at their closest point.

    Args:
        brunnel: BrunnelWay object to check alignment for
        route: Route object representing the route
        tolerance_degrees: Allowed bearing deviation in degrees

    Returns:
        True if brunnel is aligned with route within tolerance, False otherwise
    """
    if not brunnel.coords or len(brunnel.coords) < 2:
        logger.debug(
            f"Brunnel {brunnel.metadata.get('id', 'unknown')} has insufficient coordinates for bearing calculation"
        )
        return False

    if not route.positions or len(route.positions) < 2:
        logger.debug("Route has insufficient coordinates for bearing calculation")
        return False

    # Find closest segments between brunnel and route
    brunnel_segment, route_segment = find_closest_segments(
        brunnel.coords, route.positions
    )

    if brunnel_segment is None or route_segment is None:
        logger.debug(
            f"Could not find closest segments for brunnel {brunnel.metadata.get('id', 'unknown')}"
        )
        return False

    # Extract segment coordinates
    _, brunnel_start, brunnel_end = brunnel_segment
    _, route_start, route_end = route_segment

    # Calculate bearings for both segments
    brunnel_bearing = calculate_bearing(brunnel_start, brunnel_end)
    route_bearing = calculate_bearing(route_start, route_end)

    # Check if bearings are aligned
    aligned = bearings_aligned(brunnel_bearing, route_bearing, tolerance_degrees)

    logger.debug(
        f"Brunnel {brunnel.metadata.get('id', 'unknown')}: "
        f"brunnel_bearing={brunnel_bearing:.1f}°, route_bearing={route_bearing:.1f}°, "
        f"aligned={aligned} (tolerance={tolerance_degrees}°)"
    )

    return aligned


def route_spans_overlap(span1: RouteSpan, span2: RouteSpan) -> bool:
    """
    Check if two route spans overlap.

    Args:
        span1: First route span
        span2: Second route span

    Returns:
        True if the spans overlap, False otherwise
    """
    return (
        span1.start_distance_km <= span2.end_distance_km
        and span2.start_distance_km <= span1.end_distance_km
    )


def calculate_brunnel_average_distance_to_route(
    brunnel: BrunnelLike, route: Route, cumulative_distances: List[float]
) -> float:
    """
    Calculate the average distance from all points in a brunnel to the route.
    Now supports both regular and compound brunnels.

    Args:
        brunnel: BrunnelWay or CompoundBrunnelWay object to calculate distance for
        route: Route object representing the route
        cumulative_distances: Pre-calculated cumulative distances along route

    Returns:
        Average distance in kilometers, or float('inf') if calculation fails
    """
    # Get coordinates based on brunnel type
    if CompoundBrunnelWay and isinstance(brunnel, CompoundBrunnelWay):
        brunnel_coords = brunnel.coordinate_list
    else:
        brunnel_coords = brunnel.coords

    if not brunnel_coords or not route.positions:
        return float("inf")

    total_distance = 0.0
    valid_points = 0

    for brunnel_point in brunnel_coords:
        try:
            _, closest_route_point = find_closest_point_on_route(
                brunnel_point, route.positions, cumulative_distances
            )
            # Calculate direct distance between brunnel point and closest route point
            distance = haversine_distance(brunnel_point, closest_route_point)
            total_distance += distance
            valid_points += 1
        except Exception as e:
            logger.warning(f"Failed to calculate distance for brunnel point: {e}")
            continue

    if valid_points == 0:
        return float("inf")

    return total_distance / valid_points
