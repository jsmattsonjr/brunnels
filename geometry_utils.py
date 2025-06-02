#!/usr/bin/env python3
"""
Geometric operations for brunnel analysis.
"""

from typing import List, Optional
import logging
from math import cos, radians
from shapely.geometry import LineString
from geometry import Position, Geometry
from models import BrunnelWay, FilterReason, RouteSpan
from route import Route
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
    cumulative_distances = route.get_cumulative_distances()
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
    brunnel: BrunnelWay, route: Route, cumulative_distances: List[float]
) -> float:
    """
    Calculate the average distance from all points in a brunnel to the route.

    Args:
        brunnel: BrunnelWay object to calculate distance for
        route: Route object representing the route
        cumulative_distances: Pre-calculated cumulative distances along route

    Returns:
        Average distance in kilometers, or float('inf') if calculation fails
    """
    if not brunnel.coords or not route.positions:
        return float("inf")

    total_distance = 0.0
    valid_points = 0

    for brunnel_point in brunnel.coords:
        try:
            _, closest_route_point = find_closest_point_on_route(
                brunnel_point, route.positions, cumulative_distances
            )
            # Calculate direct distance between brunnel point and closest route point
            from distance_utils import haversine_distance

            distance = haversine_distance(brunnel_point, closest_route_point)
            total_distance += distance
            valid_points += 1
        except Exception as e:
            logger.warning(f"Failed to calculate distance for brunnel point: {e}")
            continue

    if valid_points == 0:
        return float("inf")

    return total_distance / valid_points


def filter_overlapping_brunnels(
    route: Route, brunnels: List[BrunnelWay], cumulative_distances: List[float]
) -> None:
    """
    Filter overlapping brunnels, keeping only the nearest one for each overlapping group.

    Args:
        route: Route object representing the route
        brunnels: List of BrunnelWay objects to filter (modified in-place)
        cumulative_distances: Pre-calculated cumulative distances along route
    """
    if not route or not brunnels:
        return

    # Only consider contained brunnels with route spans
    contained_brunnels = [
        b
        for b in brunnels
        if b.contained_in_route
        and b.route_span is not None
        and b.filter_reason == FilterReason.NONE
    ]

    if len(contained_brunnels) < 2:
        return  # Nothing to filter

    # Find groups of overlapping brunnels
    overlap_groups = []
    processed = set()

    for i, brunnel1 in enumerate(contained_brunnels):
        if i in processed:
            continue

        # Start a new group with this brunnel
        current_group = [brunnel1]
        processed.add(i)

        # Find all brunnels that overlap with any brunnel in the current group
        # Keep expanding the group until no more overlaps are found
        changed = True
        while changed:
            changed = False
            for j, brunnel2 in enumerate(contained_brunnels):
                if j in processed:
                    continue

                # Check if brunnel2 overlaps with any brunnel in current group
                for brunnel_in_group in current_group:
                    if route_spans_overlap(
                        brunnel_in_group.route_span,  # type: ignore[arg-type]
                        brunnel2.route_span,  # type: ignore[arg-type]
                    ):
                        current_group.append(brunnel2)
                        processed.add(j)
                        changed = True
                        break

        # Only add groups with more than one brunnel
        if len(current_group) > 1:
            overlap_groups.append(current_group)

    if not overlap_groups:
        logger.debug("No overlapping brunnels found")
        return

    # Filter each overlap group, keeping only the nearest
    total_filtered = 0
    for group in overlap_groups:
        logger.debug(f"Processing overlap group with {len(group)} brunnels")

        # Calculate average distance to route for each brunnel in the group
        brunnel_distances = []
        for brunnel in group:
            avg_distance = calculate_brunnel_average_distance_to_route(
                brunnel, route, cumulative_distances
            )
            brunnel_distances.append((brunnel, avg_distance))
            logger.debug(
                f"  Brunnel {brunnel.metadata.get('id', 'unknown')}: avg distance = {avg_distance:.3f}km"
            )

        # Sort by distance (closest first)
        brunnel_distances.sort(key=lambda x: x[1])

        # Keep the closest, filter the rest
        closest_brunnel, closest_distance = brunnel_distances[0]
        logger.debug(
            f"  Keeping closest: {closest_brunnel.metadata.get('id', 'unknown')} "
            f"(distance: {closest_distance:.3f}km)"
        )

        for brunnel, distance in brunnel_distances[1:]:
            brunnel.filter_reason = FilterReason.NOT_NEAREST
            brunnel.contained_in_route = False
            total_filtered += 1
            logger.debug(
                f"  Filtered: {brunnel.metadata.get('id', 'unknown')} "
                f"(distance: {distance:.3f}km, reason: {brunnel.filter_reason})"
            )

    if total_filtered > 0:
        logger.info(
            f"Filtered {total_filtered} overlapping brunnels, keeping nearest in each group"
        )
