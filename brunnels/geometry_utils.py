#!/usr/bin/env python3
"""
Simplified geometry_utils.py functions with clean polymorphism.
"""

from typing import List, Optional
import logging
from shapely.geometry import LineString

from .geometry import Position, Geometry
from .brunnel import RouteSpan

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
