# This file will contain utility functions for working with Shapely objects.
from typing import List, Optional
from shapely.geometry import LineString
from .geometry_utils import Position # Assuming Position will be moved here

def coords_to_polyline(positions: List[Position]) -> Optional[LineString]:
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
