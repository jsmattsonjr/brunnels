#!/usr/bin/env python3
"""
Updated geometry_utils.py functions to handle compound brunnels.
This shows the updated functions that need to be added/modified in geometry_utils.py
"""

from typing import List, Optional, Union
import logging
from shapely.geometry import LineString
from geometry import Position, Geometry
from brunnel_way import BrunnelWay, FilterReason, RouteSpan

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


# Backwards compatibility functions with deprecation warnings
def calculate_brunnel_route_span(
    brunnel: BrunnelWay, route, cumulative_distances: List[float]
) -> RouteSpan:
    """
    Backwards compatibility wrapper for brunnel.calculate_route_span().

    Args:
        brunnel: BrunnelWay object to calculate span for
        route: Route object representing the route
        cumulative_distances: Pre-calculated cumulative distances along route

    Returns:
        RouteSpan object with start/end distances and length
    """
    logger.warning(
        "calculate_brunnel_route_span() is deprecated. Use brunnel.calculate_route_span() instead."
    )
    return brunnel.calculate_route_span(route, cumulative_distances)


def route_contains_brunnel(route_geometry, brunnel: BrunnelWay) -> bool:
    """
    Backwards compatibility wrapper for brunnel.is_contained_by().

    Args:
        route_geometry: Shapely geometry object representing the buffered route polygon
        brunnel: BrunnelWay object to check for containment

    Returns:
        True if the route geometry completely contains the brunnel, False otherwise
    """
    logger.warning(
        "route_contains_brunnel() is deprecated. Use brunnel.is_contained_by() instead."
    )
    return brunnel.is_contained_by(route_geometry)


def check_bearing_alignment(
    brunnel: BrunnelWay, route, tolerance_degrees: float
) -> bool:
    """
    Backwards compatibility wrapper for brunnel.is_aligned_with_route().

    Args:
        brunnel: BrunnelWay object to check alignment for
        route: Route object representing the route
        tolerance_degrees: Allowed bearing deviation in degrees

    Returns:
        True if brunnel is aligned with route within tolerance, False otherwise
    """
    logger.warning(
        "check_bearing_alignment() is deprecated. Use brunnel.is_aligned_with_route() instead."
    )
    return brunnel.is_aligned_with_route(route, tolerance_degrees)


def calculate_brunnel_average_distance_to_route(
    brunnel: BrunnelLike, route, cumulative_distances: List[float]
) -> float:
    """
    Backwards compatibility wrapper for brunnel.average_distance_to_route().
    Now supports both regular and compound brunnels.

    Args:
        brunnel: BrunnelWay or CompoundBrunnelWay object to calculate distance for
        route: Route object representing the route
        cumulative_distances: Pre-calculated cumulative distances along route

    Returns:
        Average distance in kilometers, or float('inf') if calculation fails
    """
    logger.warning(
        "calculate_brunnel_average_distance_to_route() is deprecated. Use brunnel.average_distance_to_route() instead."
    )
    return brunnel.average_distance_to_route(route, cumulative_distances)
