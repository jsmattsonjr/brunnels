"""
Utility functions for working with Shapely geometries and projections.

This module provides helper functions for tasks such as creating custom
map projections (Transverse Mercator), converting coordinate lists to
Shapely LineString objects, and finding relationships between geometries
like closest segments or points at a certain distance along a line.
"""

from typing import List, Optional, Tuple
from shapely.geometry import LineString, Point
from shapely.ops import nearest_points
import pyproj
import math


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


def find_closest_segments(
    linestring1: LineString, linestring2: LineString
) -> Tuple[int, int]:
    """
    Find the closest segments between two linestrings.

    Args:
        linestring1: First linestring
        linestring2: Second linestring

    Returns:
        Tuple of (closest_segment1, closest_segment2)
    """
    point1, point2 = nearest_points(linestring1, linestring2)
    distance1 = linestring1.project(point1)
    distance2 = linestring2.project(point2)
    segment1 = linestring_distance_to_index(linestring1, distance1)
    segment2 = linestring_distance_to_index(linestring2, distance2)
    return (segment1, segment2)


def linestrings_aligned(
    linestring1: LineString, linestring2: LineString, max_angle_degrees: float
):
    # Find closest segments between linestrings projected
    idx1, idx2 = find_closest_segments(linestring1, linestring2)

    coords1 = linestring1.coords
    coords2 = linestring2.coords

    # Vector components
    # vec1_x = end_x - start_x
    vec1_x = coords1[idx1 + 1][0] - coords1[idx1][0]
    vec1_y = coords1[idx1 + 1][1] - coords1[idx1][1]
    vec2_x = coords2[idx2 + 1][0] - coords2[idx2][0]
    vec2_y = coords2[idx2 + 1][1] - coords2[idx2][1]

    # Vector magnitudes
    mag1 = math.sqrt(vec1_x**2 + vec1_y**2)
    mag2 = math.sqrt(vec2_x**2 + vec2_y**2)

    if mag1 == 0 or mag2 == 0:
        return False  # Zero-length segment

    # Normalize and dot product
    # abs() handles both parallel and anti-parallel cases
    dot_product = abs((vec1_x * vec2_x + vec1_y * vec2_y) / (mag1 * mag2))

    # Convert angle to cosine threshold
    # Ensure dot_product is not slightly > 1.0 due to precision errors
    dot_product = min(dot_product, 1.0)
    cos_max_angle = math.cos(math.radians(max_angle_degrees))

    return dot_product >= cos_max_angle
