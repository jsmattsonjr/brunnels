"""
Utility functions for working with Shapely geometries and projections.

This module provides helper functions for tasks such as creating custom
map projections (Transverse Mercator) and converting coordinate lists to
Shapely LineString objects.
"""

from typing import List, Optional, Tuple, NamedTuple
from shapely.geometry import LineString
import pyproj


class Position(NamedTuple):
    """Represents a geographic position with latitude and longitude."""

    latitude: float
    longitude: float


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
    coord_tuples: List[Tuple[float, float]], projection: Optional[pyproj.Proj] = None
) -> LineString:
    """
    Convert a list of coordinate tuples to a Shapely LineString.

    Args:
        coord_tuples: List of (longitude, latitude) tuples
        projection: Optional pyproj.Proj object for coordinate transformation.
                   If None, uses lat/lon coordinates directly.

    Returns:
        LineString object in projected coordinates if projection is provided,
        otherwise in geographic coordinates

    Raises:
        ValueError: If coord_tuples is empty or has less than 2 points
    """
    if not coord_tuples or len(coord_tuples) < 2:
        raise ValueError("At least two positions are required to create a LineString.")

    if projection is not None:
        # Transform to projected coordinates (x, y)
        lons = [pos[0] for pos in coord_tuples]
        lats = [pos[1] for pos in coord_tuples]
        x_coords, y_coords = projection(lons, lats)
        projected_coords = list(zip(x_coords, y_coords))
        return LineString(projected_coords)

    # If no projection, use coordinates as is (assumed to be in lat/lon)
    return LineString(coord_tuples)


def calculate_haversine_distance(coord1: Position, coord2: Position) -> float:
    """
    Calculate Haversine distance between two coordinates.

    Uses Haversine formula for great circle distance along the Earth's surface.

    Args:
        coord1: First coordinate position
        coord2: Second coordinate position

    Returns:
        Distance in meters
    """
    import math

    # Haversine formula for great circle distance
    lat1, lon1 = math.radians(coord1.latitude), math.radians(coord1.longitude)
    lat2, lon2 = math.radians(coord2.latitude), math.radians(coord2.longitude)

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    )

    # WGS84 equatorial radius in meters (appropriate for non-polar regions)
    earth_radius = 6378137.0
    haversine_distance = 2 * earth_radius * math.asin(math.sqrt(a))

    return haversine_distance
