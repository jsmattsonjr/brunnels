#!/usr/bin/env python3
"""
Geometric operations for brunnel analysis.
"""

from typing import List
import logging
from math import cos, radians
from shapely.geometry import LineString
from tqdm import tqdm
from models import Position, BrunnelWay

logger = logging.getLogger(__name__)


def route_intersects_brunnel(route_geometry, brunnel: BrunnelWay) -> bool:
    """
    Check if a route geometry intersects with a brunnel (bridge or tunnel).

    Args:
        route_geometry: Shapely geometry object representing the route (with buffer if applicable)
        brunnel: BrunnelWay object to check for intersection

    Returns:
        True if the route intersects the brunnel, False otherwise
    """
    if not brunnel.coords or len(brunnel.coords) < 2:
        return False

    try:
        # Convert brunnel to LineString
        brunnel_coords = [(pos.longitude, pos.latitude) for pos in brunnel.coords]
        brunnel_line = LineString(brunnel_coords)

        # Check for intersection
        return route_geometry.intersects(brunnel_line)

    except Exception as e:
        logger.warning(
            f"Failed to check intersection for brunnel {brunnel.metadata.get('id', 'unknown')}: {e}"
        )
        return False


def find_intersecting_brunnels(
    route: List[Position], brunnels: List[BrunnelWay], route_buffer_m: float = 0.0
) -> None:
    """
    Check which brunnels intersect with the route and update their intersection status.

    Args:
        route: List of Position objects representing the route
        brunnels: List of BrunnelWay objects to check (modified in-place)
        route_buffer_m: Buffer distance in meters to apply around the route (default: 0.0)
    """
    if not route:
        logger.warning("Cannot find intersections for empty route")
        return

    # Create route geometry once for all intersection checks
    route_coords = [(pos.longitude, pos.latitude) for pos in route]
    route_line = LineString(route_coords)

    # Apply buffer if specified
    if route_buffer_m > 0.0:
        # Convert buffer from meters to approximate degrees
        # Use the first route point for latitude-based longitude conversion
        avg_lat = route[0].latitude
        lat_buffer = route_buffer_m / 111000.0  # 1 degree latitude ≈ 111 km
        lon_buffer = route_buffer_m / (111000.0 * abs(cos(radians(avg_lat))))

        # Use the smaller of the two buffers to be conservative
        buffer_degrees = min(lat_buffer, lon_buffer)
        route_geometry = route_line.buffer(buffer_degrees)
    else:
        route_geometry = route_line

    intersecting_count = 0

    # Add progress bar for intersection processing
    for brunnel in tqdm(brunnels, desc="Checking intersections", unit="brunnel"):
        brunnel.intersects_route = route_intersects_brunnel(route_geometry, brunnel)
        if brunnel.intersects_route:
            intersecting_count += 1

    buffer_info = f" (with {route_buffer_m}m buffer)" if route_buffer_m > 0 else ""
    logger.info(
        f"Found {intersecting_count} brunnels intersecting the route out of {len(brunnels)} total{buffer_info}"
    )
