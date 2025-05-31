#!/usr/bin/env python3
"""
Geometric operations for brunnel analysis.
"""

from typing import List
import logging
from math import cos, radians
from shapely.geometry import LineString
from models import Position, BrunnelWay, FilterReason, RouteSpan
from distance_utils import calculate_cumulative_distances, find_closest_point_on_route

logger = logging.getLogger(__name__)


def calculate_brunnel_route_span(
    brunnel: BrunnelWay, route: List[Position], cumulative_distances: List[float]
) -> RouteSpan:
    """
    Calculate the span of a brunnel along the route.

    Args:
        brunnel: BrunnelWay object to calculate span for
        route: List of Position objects representing the route
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
            brunnel_point, route, cumulative_distances
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
    if not brunnel.coords or len(brunnel.coords) < 2:
        return False

    try:
        # Convert brunnel to LineString
        brunnel_coords = [(pos.longitude, pos.latitude) for pos in brunnel.coords]
        brunnel_line = LineString(brunnel_coords)

        # Check if route geometry completely contains the brunnel
        return route_geometry.contains(brunnel_line)

    except Exception as e:
        logger.warning(
            f"Failed to check containment for brunnel {brunnel.metadata.get('id', 'unknown')}: {e}"
        )
        return False


def find_contained_brunnels(
    route: List[Position], brunnels: List[BrunnelWay], route_buffer_m: float = 10.0
) -> None:
    """
    Check which brunnels are completely contained within the buffered route and update their containment status.
    Also calculate route spans for contained brunnels.

    Args:
        route: List of Position objects representing the route
        brunnels: List of BrunnelWay objects to check (modified in-place)
        route_buffer_m: Buffer distance in meters to apply around the route (default: 10.0, minimum: 1.0)
    """
    if not route:
        logger.warning("Cannot find contained brunnels for empty route")
        return

    # Ensure minimum buffer for containment analysis (a LineString cannot contain another LineString)
    if route_buffer_m < 1.0:
        logger.info(
            f"Minimum buffer of 1.0m required for containment analysis, using 1.0m instead of {route_buffer_m}m"
        )
        route_buffer_m = 1.0

    # Pre-calculate cumulative distances for route span calculations
    logger.info("Pre-calculating route distances...")
    cumulative_distances = calculate_cumulative_distances(route)
    total_route_distance = cumulative_distances[-1] if cumulative_distances else 0.0
    logger.info(f"Total route distance: {total_route_distance:.2f} km")

    # Create route geometry once for all containment checks
    route_coords = [(pos.longitude, pos.latitude) for pos in route]
    route_line = LineString(route_coords)

    # Convert buffer from meters to approximate degrees
    # Use the first route point for latitude-based longitude conversion
    avg_lat = route[0].latitude
    lat_buffer = route_buffer_m / 111000.0  # 1 degree latitude ≈ 111 km
    lon_buffer = route_buffer_m / (111000.0 * abs(cos(radians(avg_lat))))

    # Use the smaller of the two buffers to be conservative
    buffer_degrees = min(lat_buffer, lon_buffer)
    route_geometry = route_line.buffer(buffer_degrees)

    contained_count = 0

    # Check containment for each brunnel
    for brunnel in brunnels:
        # Only check containment for brunnels that weren't filtered by tags
        if brunnel.filter_reason == FilterReason.NONE:
            brunnel.contained_in_route = route_contains_brunnel(route_geometry, brunnel)
            if brunnel.contained_in_route:
                contained_count += 1
                # Calculate route span for contained brunnels
                try:
                    brunnel.route_span = calculate_brunnel_route_span(
                        brunnel, route, cumulative_distances
                    )
                except Exception as e:
                    logger.warning(
                        f"Failed to calculate route span for brunnel {brunnel.metadata.get('id', 'unknown')}: {e}"
                    )
                    brunnel.route_span = None
            else:
                # Set filter reason for non-contained brunnels
                brunnel.filter_reason = FilterReason.NOT_CONTAINED
        else:
            # Keep existing filter reason, don't check containment
            brunnel.contained_in_route = False

    logger.info(
        f"Found {contained_count} brunnels completely contained within the route buffer out of {len(brunnels)} total (with {route_buffer_m}m buffer)"
    )
