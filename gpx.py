#!/usr/bin/env python3
"""
GPX file parsing and validation for brunnel analysis.

Note: The main GPX parsing functionality has been moved to Route class methods:
- Route.from_gpx() replaces parse_gpx_to_route()
- Route.from_file() replaces load_gpx_route()
- Route._calculate_bbox() replaces _calculate_route_bbox()
- Route._validate_route() replaces _validate_route()

This module is kept for backwards compatibility but may be deprecated in the future.
"""

import logging

logger = logging.getLogger(__name__)

# Re-export exceptions for backwards compatibility
from route import RouteValidationError


# For backwards compatibility, provide wrapper functions that delegate to Route methods
def parse_gpx_to_route(file_input):
    """
    Backwards compatibility wrapper for Route.from_gpx().

    Args:
        file_input: File-like object containing GPX data

    Returns:
        Route object
    """
    logger.warning("parse_gpx_to_route() is deprecated. Use Route.from_gpx() instead.")
    from route import Route

    return Route.from_gpx(file_input)


def load_gpx_route(filename: str):
    """
    Backwards compatibility wrapper for Route.from_file().

    Args:
        filename: Path to GPX file, or "-" for stdin

    Returns:
        Route object
    """
    logger.warning("load_gpx_route() is deprecated. Use Route.from_file() instead.")
    from route import Route

    return Route.from_file(filename)


def _calculate_route_bbox(route, buffer_km: float = 1.0):
    """
    Backwards compatibility wrapper for Route.get_bbox().

    Args:
        route: Route object
        buffer_km: Buffer distance in kilometers

    Returns:
        Tuple of (south, west, north, east) in decimal degrees
    """
    logger.warning(
        "_calculate_route_bbox() is deprecated. Use route.get_bbox() instead."
    )
    return route.get_bbox(buffer_km)


def _validate_route(positions):
    """
    Backwards compatibility wrapper for Route._validate_route().

    Args:
        positions: List of Position objects to validate
    """
    logger.warning(
        "_validate_route() is deprecated. Use Route._validate_route() instead."
    )
    from route import Route

    return Route._validate_route(positions)
