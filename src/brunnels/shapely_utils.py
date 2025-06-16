from typing import List, Optional, Tuple
from shapely.geometry import LineString, Point
import pyproj
from .geometry_utils import Position


def create_transverse_mercator_projection(
    bbox: Tuple[float, float, float, float],
) -> pyproj.Proj:
    """
    Create a custom transverse mercator projection centered on the given bounding box.

    Args:
        bbox: Tuple of (south, west, north, east) in decimal degrees

    Returns:
        pyproj.Proj object for the custom projection
    """
    south, west, north, east = bbox

    # Calculate center of bounding box for projection center
    center_lat = (south + north) / 2.0
    center_lon = (west + east) / 2.0

    # Create custom transverse mercator projection
    proj_string = f"+proj=tmerc +lat_0={center_lat} +lon_0={center_lon} +k=1 +x_0=0 +y_0=0 +datum=WGS84 +units=m +no_defs"
    return pyproj.Proj(proj_string)


def coords_to_polyline(
    positions: List[Position], projection: Optional[pyproj.Proj] = None
) -> LineString:
    """
    Convert a list of Position objects to a Shapely LineString.

    Args:
        positions: List of Position objects
        projection: Optional pyproj.Proj object for coordinate transformation.
                   If None, uses lat/lon coordinates directly.

    Returns:
        LineString object in projected coordinates if projection is provided,
        otherwise in geographic coordinates

    Raises:
        ValueError: If positions is empty or has less than 2 points
    """
    if not positions or len(positions) < 2:
        raise ValueError("At least two positions are required to create a LineString.")

    if projection is None:
        # Use geographic coordinates (longitude, latitude)
        coords = [(pos.longitude, pos.latitude) for pos in positions]
    else:
        # Transform to projected coordinates (x, y)
        coords = []
        for pos in positions:
            x, y = projection(pos.longitude, pos.latitude)
            coords.append((x, y))

    return LineString(coords)


def linestring_distance_to_index(linestring: LineString, distance: float) -> int:
    """
    Find the highest index of a LineString coordinate whose distance from
    the start is less than the given distance.

    Args:
        linestring: The Shapely LineString
        distance: Distance along the linestring from the start

    Returns:
        Index of the coordinate (0-based)
    """
    if distance < 0:
        raise ValueError("Distance must be greater than or equal to 0")
    if distance > linestring.length:
        raise ValueError("Distance exceeds the total length of the linestring")

    coords = list(linestring.coords)

    # Walk along the linestring accumulating distances
    cumulative_distance = 0.0
    for i in range(len(coords) - 1):
        segment_start = Point(coords[i])
        segment_end = Point(coords[i + 1])
        segment_length = segment_start.distance(segment_end)

        if cumulative_distance + segment_length >= distance:
            return i

        cumulative_distance += segment_length

    return (
        len(coords) - 2
    )  # Return the last index if distance is at the end of the linestring
