from typing import List, Optional
from shapely.geometry import LineString
from .geometry_utils import Position


def coords_to_polyline(positions: List[Position]) -> LineString:
    """
    Convert a list of Position objects to a Shapely LineString.

    Args:
        positions: List of Position objects

    Returns:
        LineString object

    Raises:
        ValueError: If positions is empty or has less than 2 points
    """
    if not positions or len(positions) < 2:
        raise ValueError("At least two positions are required to create a LineString.")

    coords = [(pos.longitude, pos.latitude) for pos in positions]
    return LineString(coords)
