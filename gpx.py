#!/usr/bin/env python3
"""
GPX file parsing and validation for brunnel analysis.
"""


from typing import List, TextIO, Tuple
import sys
import logging
from math import cos, radians
import gpxpy
import gpxpy.gpx
from geometry import Position
from route import Route

logger = logging.getLogger(__name__)


class RouteValidationError(Exception):
    """Raised when route fails validation checks."""

    pass


def parse_gpx_to_route(file_input: TextIO) -> Route:
    """
    Parse GPX file and concatenate all tracks/segments into a single route.

    Args:
        file_input: File-like object containing GPX data

    Returns:
        Route object representing the concatenated route

    Raises:
        RouteValidationError: If route crosses antimeridian or approaches poles
        gpxpy.gpx.GPXException: If GPX file is malformed
    """
    try:
        gpx_data = gpxpy.parse(file_input)
    except gpxpy.gpx.GPXException as e:
        raise gpxpy.gpx.GPXException(e)

    positions = []

    # Extract all track points from all tracks and segments
    for track in gpx_data.tracks:
        for segment in track.segments:
            for point in segment.points:
                positions.append(
                    Position(
                        latitude=point.latitude,
                        longitude=point.longitude,
                        elevation=point.elevation,
                    )
                )

    route = Route(positions)

    if not route:
        logger.warning("No track points found in GPX file")
        return route

    logger.debug(f"Parsed {len(route)} track points from GPX file")

    # Validate the route
    _validate_route(route.positions)

    return route


def _calculate_route_bbox(
    route: Route, buffer_km: float = 1.0
) -> Tuple[float, float, float, float]:
    """
    Calculate bounding box for route with optional buffer.

    Args:
        route: Route object
        buffer_km: Buffer distance in kilometers (default: 1.0)

    Returns:
        Tuple of (south, west, north, east) in decimal degrees

    Raises:
        ValueError: If route is empty
    """
    if not route:
        raise ValueError("Cannot calculate bounding box for empty route")

    latitudes = [pos.latitude for pos in route]
    longitudes = [pos.longitude for pos in route]

    min_lat, max_lat = min(latitudes), max(latitudes)
    min_lon, max_lon = min(longitudes), max(longitudes)

    # Convert buffer from km to approximate degrees
    # 1 degree latitude ≈ 111 km
    # longitude varies by latitude, use average
    avg_lat = (min_lat + max_lat) / 2
    lat_buffer = buffer_km / 111.0
    lon_buffer = buffer_km / (111.0 * abs(cos(radians(avg_lat))))

    # Apply buffer (ensure we don't exceed valid coordinate ranges)
    south = max(-90.0, min_lat - lat_buffer)
    north = min(90.0, max_lat + lat_buffer)
    west = max(-180.0, min_lon - lon_buffer)
    east = min(180.0, max_lon + lon_buffer)

    logger.debug(
        f"Route bounding box: ({south:.4f}, {west:.4f}, {north:.4f}, {east:.4f}) with {buffer_km}km buffer"
    )

    return (south, west, north, east)


def _validate_route(positions: List[Position]) -> None:
    """
    Validate route for antimeridian crossing and polar proximity.

    Args:
        positions: List of Position objects to validate

    Raises:
        RouteValidationError: If validation fails
    """
    if not positions:
        return

    # Check for polar proximity (within 5 degrees of poles)
    for i, pos in enumerate(positions):
        if abs(pos.latitude) > 85.0:
            raise RouteValidationError(
                f"Route point {i} at latitude {pos.latitude:.3f}° is within "
                f"5 degrees of a pole"
            )

    # Check for antimeridian crossing
    for i in range(1, len(positions)):
        lon_diff = abs(positions[i].longitude - positions[i - 1].longitude)
        if lon_diff > 180.0:
            raise RouteValidationError(
                f"Route crosses antimeridian between points {i-1} and {i} "
                f"(longitude jump: {lon_diff:.3f}°)"
            )


def load_gpx_route(filename: str) -> Route:
    """
    Load and parse a GPX file into a route.

    Args:
        filename: Path to GPX file, or "-" for stdin

    Returns:
        Route object representing the route

    Raises:
        RouteValidationError: If route fails validation
        FileNotFoundError: If file doesn't exist
        PermissionError: If file can't be read
    """
    if filename == "-":
        logger.debug("Reading GPX data from stdin")
        return parse_gpx_to_route(sys.stdin)
    else:
        logger.debug(f"Reading GPX file: {filename}")
        with open(filename, "r", encoding="utf-8") as f:
            return parse_gpx_to_route(f)
