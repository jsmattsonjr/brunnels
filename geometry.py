#!/usr/bin/env python3
"""
Geometric operations for brunnel analysis.
"""

from typing import List, Optional
import logging
from math import cos, radians
from shapely.geometry import LineString
from models import Position, BrunnelWay, FilterReason, RouteSpan, Route
from distance_utils import (
    calculate_cumulative_distances,
    find_closest_point_on_route,
    find_closest_segments,
    calculate_bearing,
    bearings_aligned,
)

logger = logging.getLogger(__name__)


def positions_to_linestring(positions: List[Position]) -> Optional[LineString]:
    """
    Convert a list of Position objects to a Shapely LineString.

    Args:
        positions: List of Position objects

    Returns:
        LineString object, or None if positions is empty or has less than 2 points
    """
    if not positions or len(positions) < 2:
        return None

    coords = [(pos.longitude, pos.latitude) for pos in positions]
    return LineString(coords)


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


def find_contained_brunnels(
    route: Route,
    brunnels: List[BrunnelWay],
    route_buffer_m: float,
    bearing_tolerance_degrees: float,
) -> None:
    """
    Check which brunnels are completely contained within the buffered route and aligned with route bearing.
    Updates their containment status and calculates route spans for contained brunnels.

    Args:
        route: Route object representing the route
        brunnels: List of BrunnelWay objects to check (modified in-place)
        route_buffer_m: Buffer distance in meters to apply around the route (default: 10.0, minimum: 1.0)
        bearing_tolerance_degrees: Bearing alignment tolerance in degrees (default: 20.0)
    """
    if not route:
        logger.warning("Cannot find contained brunnels for empty route")
        return

    # Ensure minimum buffer for containment analysis (a LineString cannot contain another LineString)
    if route_buffer_m < 1.0:
        logger.warning(
            f"Minimum buffer of 1.0m required for containment analysis, using 1.0m instead of {route_buffer_m}m"
        )
        route_buffer_m = 1.0

    # Pre-calculate cumulative distances for route span calculations
    logger.debug("Pre-calculating route distances...")
    cumulative_distances = calculate_cumulative_distances(route.positions)
    total_route_distance = cumulative_distances[-1] if cumulative_distances else 0.0
    logger.info(f"Total route distance: {total_route_distance:.2f} km")

    # Get memoized LineString from route
    route_line = route.get_linestring()
    if route_line is None:
        logger.warning("Cannot create LineString for route")
        return

    # Convert buffer from meters to approximate degrees
    # Use the first route point for latitude-based longitude conversion
    avg_lat = route[0].latitude
    lat_buffer = route_buffer_m / 111000.0  # 1 degree latitude ≈ 111 km
    lon_buffer = route_buffer_m / (111000.0 * abs(cos(radians(avg_lat))))

    # Use the smaller of the two buffers to be conservative
    buffer_degrees = min(lat_buffer, lon_buffer)
    route_geometry = route_line.buffer(buffer_degrees)

    # Check if buffered geometry is valid (can be invalid with self-intersecting routes)
    if not route_geometry.is_valid:
        logger.warning(
            f"Buffered route geometry is invalid (likely due to self-intersecting route). "
            f"Attempting to fix with buffer(0)"
        )
        try:
            route_geometry = route_geometry.buffer(0)
            if route_geometry.is_valid:
                logger.info("Successfully fixed invalid geometry")
            else:
                logger.warning(
                    "Could not fix invalid geometry - containment results may be unreliable"
                )
        except Exception as e:
            logger.warning(f"Failed to fix invalid geometry: {e}")

    contained_count = 0
    unaligned_count = 0

    # Check containment for each brunnel
    for brunnel in brunnels:
        # Only check containment for brunnels that weren't filtered by tags
        if brunnel.filter_reason == FilterReason.NONE:
            brunnel.contained_in_route = route_contains_brunnel(route_geometry, brunnel)
            if brunnel.contained_in_route:
                # Check bearing alignment for contained brunnels
                if check_bearing_alignment(brunnel, route, bearing_tolerance_degrees):
                    # Calculate route span for aligned, contained brunnels
                    try:
                        brunnel.route_span = calculate_brunnel_route_span(
                            brunnel, route, cumulative_distances
                        )
                        contained_count += 1
                    except Exception as e:
                        logger.warning(
                            f"Failed to calculate route span for brunnel {brunnel.metadata.get('id', 'unknown')}: {e}"
                        )
                        logger.warning(f"Evicting brunnel from contained set")
                        brunnel.filter_reason = FilterReason.NO_ROUTE_SPAN
                        brunnel.contained_in_route = False
                        brunnel.route_span = None
                else:
                    # Mark as unaligned and remove from contained set
                    brunnel.filter_reason = FilterReason.UNALIGNED
                    brunnel.contained_in_route = False
                    brunnel.route_span = None
                    unaligned_count += 1
            else:
                # Set filter reason for non-contained brunnels
                brunnel.filter_reason = FilterReason.NOT_CONTAINED
        else:
            # Keep existing filter reason, don't check containment
            brunnel.contained_in_route = False

    logger.debug(
        f"Found {contained_count} brunnels completely contained and aligned within the route buffer "
        f"out of {len(brunnels)} total (with {route_buffer_m}m buffer, {bearing_tolerance_degrees}° tolerance)"
    )

    if unaligned_count > 0:
        logger.debug(f"Filtered {unaligned_count} brunnels due to bearing misalignment")
