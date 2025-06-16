from typing import List, Optional, Tuple
from shapely.geometry import LineString
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
