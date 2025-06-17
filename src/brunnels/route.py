#!/usr/bin/env python3
"""
Route data model for brunnel analysis.
"""

from typing import Optional, Tuple, List, TextIO, Dict, Any
from dataclasses import dataclass, field
import logging
import math
from math import cos, radians
import argparse
import gpxpy
import gpxpy.gpx
from shapely.geometry.base import BaseGeometry
from shapely.geometry import LineString, Point
import pyproj

from .geometry_utils import Position
from .brunnel import Brunnel, FilterReason
from .overpass import query_overpass_brunnels
from .shapely_utils import coords_to_polyline, create_transverse_mercator_projection

logger = logging.getLogger(__name__)


class Route:
    """Represents a GPX route with memoized geometric operations."""

    def __init__(self, coords: List[Position]):
        if not coords:
            raise ValueError("Route coordinates cannot be empty")
        if len(coords) < 2:
            raise ValueError("Route must have at least two coordinates")
        self.coords = coords
        self.bbox = self._calculate_bbox()

        # Create projection based on route bounding box
        self.projection = create_transverse_mercator_projection(self.bbox)

        coord_tuples = [(pos.longitude, pos.latitude) for pos in self.coords]
        self.linestring: LineString = coords_to_polyline(coord_tuples, self.projection)

    def get_bbox(self, buffer: float = 0.0) -> Tuple[float, float, float, float]:
        """
        Get bounding box for this route, optionally with a buffer.
        The internally stored _bbox is always without a buffer.

        Args:
            buffer: Buffer distance in meters (default: 0.0)

        Returns:
            Tuple of (south, west, north, east) in decimal degrees

        Raises:
            ValueError: If route is empty
        """
        if not self.coords:
            raise ValueError("Cannot calculate bounding box for empty route")

        # Ensure the base bounding box (0 buffer) is calculated and memoized
        if self.bbox is None:
            self.bbox = self._calculate_bbox()

        # If no buffer is requested, return the memoized base bounding box
        if buffer == 0.0:
            return self.bbox

        # If a buffer is requested, calculate it based on the memoized _bbox
        min_lat, min_lon, max_lat, max_lon = self.bbox

        # Convert buffer from m to approximate degrees
        # 1 degree latitude ≈ 111 km = 111000m
        # longitude varies by latitude, use average of the base bbox
        avg_lat = (min_lat + max_lat) / 2
        lat_buffer = buffer / 111000.0
        lon_buffer = buffer / (111000.0 * abs(cos(radians(avg_lat))))

        # Apply buffer (ensure we don't exceed valid coordinate ranges)
        buffered_south = max(-90.0, min_lat - lat_buffer)
        buffered_north = min(90.0, max_lat + lat_buffer)
        buffered_west = max(-180.0, min_lon - lon_buffer)
        buffered_east = min(180.0, max_lon + lon_buffer)

        logger.debug(
            f"Returning on-the-fly buffered bounding box: ({buffered_south:.4f}, {buffered_west:.4f}, {buffered_north:.4f}, {buffered_east:.4f}) with {buffer}m buffer from base _bbox"
        )
        return (buffered_south, buffered_west, buffered_north, buffered_east)

    def _calculate_bbox(self) -> Tuple[float, float, float, float]:
        """
        Calculate bounding box for route, always with a 0 buffer.

        Returns:
            Tuple of (south, west, north, east) in decimal degrees
        """
        latitudes = [coord.latitude for coord in self.coords]
        longitudes = [coord.longitude for coord in self.coords]

        min_lat, max_lat = min(latitudes), max(latitudes)
        min_lon, max_lon = min(longitudes), max(longitudes)

        # Buffer is always 0 for the base calculation.
        # The actual `buffer` parameter passed to this method is ignored.
        internal_buffer_value = 0.0
        lat_buffer = 0.0  # Since internal_buffer_value is 0
        lon_buffer = 0.0  # Since internal_buffer_value is 0

        # Apply 0 buffer (effectively just taking min/max values)
        south = max(-90.0, min_lat - lat_buffer)
        north = min(90.0, max_lat + lat_buffer)
        west = max(-180.0, min_lon - lon_buffer)
        east = min(180.0, max_lon + lon_buffer)

        logger.debug(
            f"Base route bounding box calculated: ({south:.4f}, {west:.4f}, {north:.4f}, {east:.4f}) with {internal_buffer_value}m buffer"
        )

        return (south, west, north, east)

    def filter_overlapping_brunnels(
        self,
        brunnels: Dict[str, Brunnel],
    ) -> None:
        """
        Filter overlapping brunnels, keeping only the nearest one for each overlapping group.
        Supports both regular and compound brunnels.

        Args:
            brunnels: Dictionary of Brunnel objects to filter (modified in-place)
        """
        if not self.coords or not brunnels:
            return

        # Only consider contained brunnels with route spans
        contained_brunnels = [
            b
            for b in brunnels.values()
            if b.is_representative()
            and b.get_route_span() is not None
            and b.filter_reason == FilterReason.NONE
        ]

        if len(contained_brunnels) < 2:
            return  # Nothing to filter

        # Find groups of overlapping brunnels
        overlap_groups = []
        processed = set()

        for i, brunnel1 in enumerate(contained_brunnels):
            if i in processed:
                continue

            # Start a new group with this brunnel
            current_group = [brunnel1]
            processed.add(i)

            # Find all brunnels that overlap with any brunnel in the current group
            changed = True
            while changed:
                changed = False
                for j, brunnel2 in enumerate(contained_brunnels):
                    if j in processed:
                        continue

                    # Check if brunnel2 overlaps with any brunnel in current group
                    for brunnel_in_group in current_group:
                        if brunnel_in_group.overlaps_with(brunnel2):
                            current_group.append(brunnel2)
                            processed.add(j)
                            changed = True
                            break

            # Only add groups with more than one brunnel
            if len(current_group) > 1:
                overlap_groups.append(current_group)

        if not overlap_groups:
            logger.debug("No overlapping brunnels found")
            return

        # Filter each overlap group, keeping only the nearest
        filtered = 0
        for group in overlap_groups:
            logger.debug(f"Processing overlap group with {len(group)} brunnels")

            # Calculate average distance to route for each brunnel in the group
            brunnel_distances = []
            for brunnel in group:
                avg_distance = self.average_distance_to_brunnel(brunnel)
                brunnel_distances.append((brunnel, avg_distance))
                logger.debug(
                    f"  {brunnel.get_short_description()}: avg distance = {avg_distance:.3f}km"
                )

            # Sort by distance (closest first)
            brunnel_distances.sort(key=lambda x: x[1])

            # Keep the closest, filter the rest
            closest_brunnel, closest_distance = brunnel_distances[0]

            logger.debug(
                f"  Keeping closest: {closest_brunnel.get_short_description()} (distance: {closest_distance:.3f}km)"
            )

            for brunnel, distance in brunnel_distances[1:]:
                brunnel.filter_reason = FilterReason.NOT_NEAREST
                filtered += 1

                logger.debug(
                    f"  Filtered: {brunnel.get_short_description()} (distance: {distance:.3f}km, reason: {brunnel.filter_reason})"
                )

        if filtered > 0:
            logger.debug(
                f"Filtered {filtered} overlapping brunnels, keeping nearest in each group"
            )

    def find_brunnels(self, args: argparse.Namespace) -> Dict[str, Brunnel]:
        """
        Find all bridges and tunnels near this route and check for containment within route buffer.

        Args:
            args: argparse.Namespace object containing all settings

        Returns:
            List of Brunnel objects found near the route, with containment status set
        """
        if not self.coords:
            raise ValueError("Cannot find brunnels for empty route")

        bbox = self.get_bbox(args.bbox_buffer)

        # Calculate and log query area before API call
        south, west, north, east = bbox
        lat_diff = north - south
        lon_diff = east - west
        avg_lat = (north + south) / 2
        lat_km = lat_diff * 111.0
        lon_km = lon_diff * 111.0 * abs(math.cos(math.radians(avg_lat)))
        area_sq_km = lat_km * lon_km

        logger.debug(
            f"Querying Overpass API for bridges and tunnels in {area_sq_km:.1f} sq km area..."
        )

        raw_ways = query_overpass_brunnels(bbox, args)

        brunnels = {}
        for way_data in raw_ways:
            try:
                brunnel = Brunnel.from_overpass_data(way_data, self.projection)
                brunnels[brunnel.get_id()] = brunnel
            except (KeyError, ValueError) as e:
                logger.warning(f"Failed to parse brunnel way: {e}")
                continue

        return brunnels

    def average_distance_to_brunnel(self, brunnel: Brunnel) -> float:
        """
        Calculate the average distance from all points in a brunnel to the closest points on this route.

        Args:
            brunnel: Brunnel object to calculate distances for
        Returns:
            Average distance in kilometers
        """

        points = [Point(coord) for coord in brunnel.linestring.coords]

        total_distance = 0.0

        for point in points:
            total_distance += point.distance(self.linestring)

        return total_distance / len(points) / 1000.0  # Convert to kilometers

    @classmethod
    def from_gpx(cls, file_input: TextIO) -> "Route":
        """
        Parse GPX file and concatenate all tracks/segments into a single route.

        Args:
            file_input: File-like object containing GPX data

        Returns:
            Route object representing the concatenated route

        Raises:
            UnsupprtedRouteError: If route crosses antimeridian or approaches poles
            gpxpy.gpx.GPXException: If GPX file is malformed
        """
        try:
            gpx_data = gpxpy.parse(file_input)
        except gpxpy.gpx.GPXException as e:
            raise gpxpy.gpx.GPXException(e)

        coords_data = []

        # Extract all track points from all tracks and segments
        for track in gpx_data.tracks:
            for segment in track.segments:
                for point in segment.points:
                    coords_data.append(
                        Position(
                            latitude=point.latitude,
                            longitude=point.longitude,
                        )
                    )

        # Note: The __init__ method will raise ValueError if coords_data is empty or has less than 2 points.
        route = cls(coords_data)

        logger.debug(f"Parsed {len(route.coords)} track points from GPX file")

        # Check the route
        cls._check_route(route.coords)

        return route

    @classmethod
    def from_file(cls, filename: str) -> "Route":
        """
        Load and parse a GPX file into a route.

        Args:
            filename: Path to GPX file

        Returns:
            Route object representing the route

        Raises:
            UnsupprtedRouteError: If route fails validation
            FileNotFoundError: If file doesn't exist
            PermissionError: If file can't be read
        """
        logger.debug(f"Reading GPX file: {filename}")
        with open(filename, "r", encoding="utf-8") as f:
            return cls.from_gpx(f)

    @classmethod
    def from_positions(cls, positions: List[Position]) -> "Route":
        """
        Create a Route from a list of Position objects.

        Args:
            positions: List of Position objects

        Returns:
            Route object representing the route
        """
        # Note: The __init__ method will raise ValueError if positions is empty or has less than 2 points.
        # The factory method should probably also raise an error earlier if desired for empty lists,
        # or rely on __init__ to do so. For now, let __init__ handle it.
        route = cls(positions)

        # Check the route
        cls._check_route(route.coords)

        return route

    @staticmethod
    def _check_route(coords: List[Position]) -> None:
        """
        Check route for antimeridian crossing and polar proximity.

        Args:
            coords: List of Position objects to check

        Raises:
            RuntimeError: If route is unsupported
        """
        if not coords:
            return

        # Check for polar proximity (within 5 degrees of poles)
        for i, coord in enumerate(coords):
            if abs(coord.latitude) > 85.0:
                raise RuntimeError(
                    f"Route point {i} at latitude {coord.latitude:.3f}° is within "
                    f"5 degrees of a pole"
                )

        # Check for antimeridian crossing
        for i in range(1, len(coords)):
            lon_diff = abs(coords[i].longitude - coords[i - 1].longitude)
            if lon_diff > 180.0:
                raise RuntimeError(
                    f"Route crosses antimeridian between points {i-1} and {i} "
                    f"(longitude jump: {lon_diff:.3f}°)"
                )

    def __len__(self) -> int:
        """Return number of trackpoints in route."""
        return len(self.coords)

    def __getitem__(self, index):
        """Allow indexing into trackpoints."""
        return self.coords[index]

    def __iter__(self):
        """Allow iteration over trackpoints."""
        return iter(self.coords)

    def calculate_buffered_route_geometry(self, route_buffer: float) -> BaseGeometry:
        """
        Calculate the buffered Shapely geometry for the route.

        Args:
            route_buffer: Buffer distance in meters.

        Returns:
            Shapely geometry object or None if it could not be created.
        """
        if not self.coords:
            raise ValueError(
                "Cannot calculate buffered geometry for empty route, coords are empty"
            )

        route_line = self.linestring
        if route_line is None:
            raise ValueError(
                "Cannot calculate buffered geometry because LineString is None"
            )

        if route_buffer <= 0:
            raise ValueError(
                f"Route buffer must be positive, got {route_buffer} meters"
            )

        # Since we're now using projected coordinates in meters,
        # we can use the buffer distance directly
        route_geometry = route_line.buffer(route_buffer)

        if not route_geometry.is_valid:
            logger.warning(
                "Initial buffered route geometry is invalid. Attempting to fix with buffer(0)."
            )
            fixed_geometry = route_geometry.buffer(0)
            if fixed_geometry.is_valid:
                logger.warning("Successfully fixed invalid buffered geometry.")
                return fixed_geometry
            else:
                raise ValueError(
                    "Could not fix invalid buffered geometry after attempting buffer(0). "
                    "The geometry remains invalid."
                )
        return route_geometry

    def filter_misaligned_brunnels(
        self,
        brunnels: Dict[str, Brunnel],
        bearing_tolerance_degrees: float,
    ) -> None:
        """
        Filters a list of brunnels by their alignment with the route.

        Args:

            bearing_tolerance_degrees: Bearing alignment tolerance in degrees.
            self: The Route instance.

        """
        unaligned_count = 0

        for brunnel in brunnels.values():

            if (
                brunnel.filter_reason == FilterReason.NONE
                and not brunnel.is_aligned_with_route(self, bearing_tolerance_degrees)
            ):
                brunnel.filter_reason = FilterReason.UNALIGNED
                unaligned_count += 1

        if unaligned_count > 0:
            logger.debug(
                f"Filtered {unaligned_count} brunnels out of {len(brunnels)} "
                f"contained brunnels due to bearing misalignment (tolerance: {bearing_tolerance_degrees}°)"
            )

    def calculate_route_spans(self, brunnels: Dict[str, Brunnel]) -> None:
        """
        Calculate the route span for each included brunnel.
        """
        for brunnel in brunnels.values():
            if brunnel.filter_reason == FilterReason.NONE:
                brunnel.calculate_route_span(self)
