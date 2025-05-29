#!/usr/bin/env python3
"""
GPX file parsing and validation for brunnel analysis.
"""


from typing import List, TextIO
import sys
import logging
import gpxpy
import gpxpy.gpx
from brunnels import Position

logger = logging.getLogger(__name__)


class RouteValidationError(Exception):
    """Raised when route fails validation checks."""

    pass


def parse_gpx_to_route(file_input: TextIO) -> List[Position]:
    """
    Parse GPX file and concatenate all tracks/segments into a single route.

    Args:
        file_input: File-like object containing GPX data

    Returns:
        List of Position objects representing the concatenated route

    Raises:
        RouteValidationError: If route crosses antimeridian or approaches poles
        gpxpy.gpx.GPXException: If GPX file is malformed
    """
    try:
        gpx_data = gpxpy.parse(file_input)
    except gpxpy.gpx.GPXException as e:
        raise gpxpy.gpx.GPXException(e)

    route = []

    # Extract all track points from all tracks and segments
    for track in gpx_data.tracks:
        for segment in track.segments:
            for point in segment.points:
                route.append(
                    Position(
                        latitude=point.latitude,
                        longitude=point.longitude,
                        elevation=point.elevation,
                    )
                )

    if not route:
        logger.warning("No track points found in GPX file")
        return route

    logger.info(f"Parsed {len(route)} track points from GPX file")

    # Validate the route
    _validate_route(route)

    return route


def _validate_route(route: List[Position]) -> None:
    """
    Validate route for antimeridian crossing and polar proximity.

    Args:
        route: List of Position objects to validate

    Raises:
        RouteValidationError: If validation fails
    """
    if not route:
        return

    # Check for polar proximity (within 5 degrees of poles)
    for i, pos in enumerate(route):
        if abs(pos.latitude) > 85.0:
            raise RouteValidationError(
                f"Route point {i} at latitude {pos.latitude:.3f}° is within "
                f"5 degrees of a pole"
            )

    # Check for antimeridian crossing
    for i in range(1, len(route)):
        lon_diff = abs(route[i].longitude - route[i - 1].longitude)
        if lon_diff > 180.0:
            raise RouteValidationError(
                f"Route crosses antimeridian between points {i-1} and {i} "
                f"(longitude jump: {lon_diff:.3f}°)"
            )


def load_gpx_route(filename: str) -> List[Position]:
    """
    Load and parse a GPX file into a route.

    Args:
        filename: Path to GPX file, or "-" for stdin

    Returns:
        List of Position objects representing the route

    Raises:
        RouteValidationError: If route fails validation
        FileNotFoundError: If file doesn't exist
        PermissionError: If file can't be read
    """
    if filename == "-":
        logger.info("Reading GPX data from stdin")
        return parse_gpx_to_route(sys.stdin)
    else:
        logger.info(f"Reading GPX file: {filename}")
        with open(filename, "r", encoding="utf-8") as f:
            return parse_gpx_to_route(f)
