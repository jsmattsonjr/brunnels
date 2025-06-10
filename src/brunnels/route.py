#!/usr/bin/env python3
"""
Route data model for brunnel analysis.
"""

from typing import Optional, Tuple, List, TextIO, Sequence, Dict, Any
from dataclasses import dataclass, field
import logging
import math
from math import cos, radians
import gpxpy
import gpxpy.gpx

from .geometry import Position, Geometry
from .geometry_utils import (
    find_closest_point_on_route,
    haversine_distance,
)
from .config import BrunnelsConfig
from .brunnel import Brunnel, BrunnelType, FilterReason, RouteSpan
from .brunnel_way import BrunnelWay
from .overpass import query_overpass_brunnels

logger = logging.getLogger(__name__)


class RouteValidationError(Exception):
    """Raised when route fails validation checks."""

    pass


@dataclass
class Route(Geometry):
    """Represents a GPX route with memoized geometric operations."""

    trackpoints: List[Dict[str, Any]]
    _bbox: Optional[Tuple[float, float, float, float]] = field(
        default=None, init=False, repr=False
    )

    @property
    def coordinate_list(self) -> List[Position]:
        """Return the list of Position objects for this geometry."""
        # Convert trackpoints to Position objects
        return [
            Position(
                latitude=tp["latitude"],
                longitude=tp["longitude"],
                elevation=tp.get("elevation"),  # Use .get for optional elevation
            )
            for tp in self.trackpoints
        ]

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
        if not self.trackpoints:
            raise ValueError("Cannot calculate bounding box for empty route")

        # Ensure the base bounding box (0 buffer) is calculated and memoized
        if self._bbox is None:
            self._bbox = self._calculate_bbox(0.0)

        # If no buffer is requested, return the memoized base bounding box
        if buffer == 0.0:
            return self._bbox

        # If a buffer is requested, calculate it based on the memoized _bbox
        min_lat, min_lon, max_lat, max_lon = self._bbox

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

    def _calculate_bbox(
        self, ignored_buffer: float
    ) -> Tuple[float, float, float, float]:
        """
        Calculate bounding box for route, always with a 0 buffer.
        The `ignored_buffer` parameter is kept for compatibility with previous calls
        but is no longer used internally for calculations.

        Args:
            ignored_buffer: This parameter is ignored. The calculation always uses a 0m buffer.

        Returns:
            Tuple of (south, west, north, east) in decimal degrees
        """
        latitudes = [tp["latitude"] for tp in self.trackpoints]
        longitudes = [tp["longitude"] for tp in self.trackpoints]

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

    def find_contained_brunnels(
        self,
        brunnels: List[Brunnel],
        route_buffer: float,
        bearing_tolerance_degrees: float,
    ) -> None:
        """
        Check which brunnels are completely contained within the buffered route and aligned with route bearing.
        Updates their containment status and calculates route spans for contained brunnels.

        Args:
            brunnels: List of Brunnel objects to check (modified in-place)
            route_buffer: Buffer distance in meters to apply around the route (minimum: 1.0)
            bearing_tolerance_degrees: Bearing alignment tolerance in degrees
        """
        if not self.trackpoints:
            logger.warning("Cannot find contained brunnels for empty route")
            return

        # Ensure minimum buffer for containment analysis
        if route_buffer < 1.0:
            logger.warning(
                f"Minimum buffer of 1.0m required for containment analysis, using 1.0m instead of {route_buffer}m"
            )
            route_buffer = 1.0

        # Get memoized LineString from route
        route_line = self.get_linestring()
        if route_line is None:
            logger.warning("Cannot create LineString for route")
            return

        # Convert buffer from meters to approximate degrees
        avg_lat = self.trackpoints[0]["latitude"]
        lat_buffer = route_buffer / 111000.0  # 1 degree latitude ≈ 111 km
        lon_buffer = route_buffer / (111000.0 * abs(cos(radians(avg_lat))))

        # Use the smaller of the two buffers to be conservative
        buffer_degrees = min(lat_buffer, lon_buffer)
        route_geometry = route_line.buffer(buffer_degrees)

        # Check if buffered geometry is valid
        if not route_geometry.is_valid:
            logger.warning(
                f"Buffered route geometry is invalid (likely due to self-intersecting route). "
                f"Attempting to fix with buffer(0)"
            )
            try:
                route_geometry = route_geometry.buffer(0)
                if route_geometry.is_valid:
                    logger.warning("Successfully fixed invalid geometry")
                else:
                    logger.warning(
                        "Could not fix invalid geometry - containment results may be unreliable"
                    )
            except Exception as e:
                logger.warning(f"Failed to fix invalid geometry: {e}")

        contained_count = 0
        unaligned_count = 0

        # Check containment for each brunnel
        for brunnel in brunnels:
            # Only check containment for brunnels that weren't filtered by tags
            if brunnel.filter_reason == FilterReason.NONE:
                brunnel.contained_in_route = brunnel.is_contained_by(route_geometry)
                if brunnel.contained_in_route:
                    # Check bearing alignment for contained brunnels
                    if brunnel.is_aligned_with_route(self, bearing_tolerance_degrees):
                        # Calculate route span for aligned, contained brunnels
                        try:
                            brunnel.route_span = brunnel.calculate_route_span(self)
                            contained_count += 1
                        except Exception as e:
                            logger.warning(
                                f"Failed to calculate route span for brunnel {brunnel.get_id()}: {e}"
                            )
                            logger.warning(f"Evicting brunnel from contained set")
                            brunnel.filter_reason = FilterReason.NO_ROUTE_SPAN
                            brunnel.contained_in_route = False
                            brunnel.route_span = None
                    else:
                        # Mark as unaligned and remove from contained set
                        brunnel.filter_reason = FilterReason.UNALIGNED
                        brunnel.contained_in_route = False
                        brunnel.route_span = None
                        unaligned_count += 1
                else:
                    # Set filter reason for non-contained brunnels
                    brunnel.filter_reason = FilterReason.NOT_CONTAINED
            else:
                # Keep existing filter reason, don't check containment
                brunnel.contained_in_route = False

        logger.debug(
            f"Found {contained_count} brunnels completely contained and aligned within the route buffer "
            f"out of {len(brunnels)} total (with {route_buffer}m buffer, {bearing_tolerance_degrees}° tolerance)"
        )

        if unaligned_count > 0:
            logger.debug(
                f"Filtered {unaligned_count} brunnels due to bearing misalignment"
            )

    def filter_overlapping_brunnels(
        self,
        brunnels: Sequence[Brunnel],
    ) -> None:
        """
        Filter overlapping brunnels, keeping only the nearest one for each overlapping group.
        Supports both regular and compound brunnels.

        Args:
            brunnels: List of Brunnel objects to filter (modified in-place)
        """
        if not self.trackpoints or not brunnels:
            return

        # Only consider contained brunnels with route spans
        contained_brunnels = [
            b
            for b in brunnels
            if b.contained_in_route
            and b.route_span is not None
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
                        if route_spans_overlap(
                            brunnel_in_group.route_span,  # type: ignore
                            brunnel2.route_span,  # type: ignore
                        ):
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
                avg_distance = self.average_distance_to_polyline(brunnel)
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
                brunnel.contained_in_route = False
                filtered += 1

                logger.debug(
                    f"  Filtered: {brunnel.get_short_description()} (distance: {distance:.3f}km, reason: {brunnel.filter_reason})"
                )

        if filtered > 0:
            logger.debug(
                f"Filtered {filtered} overlapping brunnels, keeping nearest in each group"
            )

    def find_brunnels(self, config: BrunnelsConfig) -> List[BrunnelWay]:
        """
        Find all bridges and tunnels near this route and check for containment within route buffer.

        Args:
            config: BrunnelsConfig object containing all settings

        Returns:
            List of BrunnelWay objects found near the route, with containment status set
        """
        if not self.trackpoints:
            logger.warning("Cannot find brunnels for empty route")
            return []

        bbox = self.get_bbox(config.bbox_buffer)

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
        raw_ways = query_overpass_brunnels(bbox)

        brunnels = []
        filtered_count = 0
        for way_data in raw_ways:
            try:
                brunnel = BrunnelWay.from_overpass_data(way_data)

                # Count filtered brunnels but keep them for visualization
                if brunnel.filter_reason != FilterReason.NONE:
                    filtered_count += 1

                brunnels.append(brunnel)
            except (KeyError, ValueError) as e:
                logger.warning(f"Failed to parse brunnel way: {e}")
                continue

        logger.info(f"Found {len(brunnels)} brunnels near route")

        if filtered_count > 0:
            logger.debug(f"{filtered_count} brunnels filtered (will show greyed out)")

        # Check for containment within the route buffer and bearing alignment
        self.find_contained_brunnels(
            brunnels, config.route_buffer, config.bearing_tolerance
        )

        # Count contained vs total brunnels
        bridges = [b for b in brunnels if b.brunnel_type == BrunnelType.BRIDGE]
        tunnels = [b for b in brunnels if b.brunnel_type == BrunnelType.TUNNEL]
        contained_bridges = [b for b in bridges if b.contained_in_route]
        contained_tunnels = [b for b in tunnels if b.contained_in_route]

        logger.debug(
            f"Found {len(contained_bridges)}/{len(bridges)} contained bridges and {len(contained_tunnels)}/{len(tunnels)} contained tunnels"
        )

        return brunnels

    def average_distance_to_polyline(self, geometry: Geometry) -> float:
        """
        Calculate the average distance from all points in a geometry to the closest points on this route.

        Args:
            geometry: Any Geometry object (BrunnelWay, CompoundBrunnelWay, etc.)

        Returns:
            Average distance in kilometers, or float('inf') if calculation fails
        """
        geometry_coords = geometry.coordinate_list

        if not geometry_coords or not self.trackpoints:
            return float("inf")

        total_distance = 0.0
        valid_points = 0

        for geometry_point in geometry_coords:
            try:
                _, closest_route_point = find_closest_point_on_route(
                    geometry_point, self
                )
                # Calculate direct distance between geometry point and closest route point
                distance = haversine_distance(geometry_point, closest_route_point)
                total_distance += distance
                valid_points += 1
            except Exception as e:
                logger.warning(f"Failed to calculate distance for geometry point: {e}")
                continue

        if valid_points == 0:
            return float("inf")

        return total_distance / valid_points

    def calculate_distances(self) -> None:
        """
        Calculate and set track_distance for each trackpoint.

        Sets trackpoint[0]["track_distance"] to 0 and trackpoint[i]["track_distance"]
        to trackpoint[i-1]["track_distance"] plus the haversine distance from
        trackpoint[i-1] to trackpoint[i].
        """
        if not self.trackpoints:
            return

        # Set first trackpoint distance to 0
        self.trackpoints[0]["track_distance"] = 0.0

        # Calculate cumulative distances for remaining trackpoints
        for i in range(1, len(self.trackpoints)):
            prev_point = Position(
                latitude=self.trackpoints[i - 1]["latitude"],
                longitude=self.trackpoints[i - 1]["longitude"],
                elevation=self.trackpoints[i - 1].get("elevation"),
            )
            curr_point = Position(
                latitude=self.trackpoints[i]["latitude"],
                longitude=self.trackpoints[i]["longitude"],
                elevation=self.trackpoints[i].get("elevation"),
            )

            # Calculate distance from previous point and add to cumulative distance
            segment_distance = haversine_distance(prev_point, curr_point)
            self.trackpoints[i]["track_distance"] = (
                self.trackpoints[i - 1]["track_distance"] + segment_distance
            )

    @classmethod
    def from_gpx(cls, file_input: TextIO) -> "Route":
        """
        Parse GPX file and concatenate all tracks/segments into a single route.

        Args:
            file_input: File-like object containing GPX data

        Returns:
            Route object representing the concatenated route

        Raises:
            RouteValidationError: If route crosses antimeridian or approaches poles
            gpxpy.gpx.GPXException: If GPX file is malformed
        """
        try:
            gpx_data = gpxpy.parse(file_input)
        except gpxpy.gpx.GPXException as e:
            raise gpxpy.gpx.GPXException(e)

        trackpoints_data = []

        # Extract all track points from all tracks and segments
        for track in gpx_data.tracks:
            for segment in track.segments:
                for point in segment.points:
                    trackpoints_data.append(
                        {
                            "latitude": point.latitude,
                            "longitude": point.longitude,
                            "elevation": point.elevation,
                        }
                    )

        route = cls(trackpoints_data)

        if not route:
            logger.warning("No track points found in GPX file")
            return route

        logger.debug(f"Parsed {len(route)} track points from GPX file")

        # Validate the route
        cls._validate_route(route.trackpoints)

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
            RouteValidationError: If route fails validation
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
        if not positions:
            return cls([])

        trackpoints_data = [
            {
                "latitude": pos.latitude,
                "longitude": pos.longitude,
                "elevation": pos.elevation,
            }
            for pos in positions
        ]

        route = cls(trackpoints_data)

        # Validate the route
        cls._validate_route(route.trackpoints)

        return route

    @staticmethod
    def _validate_route(trackpoints: List[Dict[str, Any]]) -> None:
        """
        Validate route for antimeridian crossing and polar proximity.

        Args:
            trackpoints: List of trackpoint dictionaries to validate

        Raises:
            RouteValidationError: If validation fails
        """
        if not trackpoints:
            return

        # Check for polar proximity (within 5 degrees of poles)
        for i, tp in enumerate(trackpoints):
            if abs(tp["latitude"]) > 85.0:
                raise RouteValidationError(
                    f"Route point {i} at latitude {tp['latitude']:.3f}° is within "
                    f"5 degrees of a pole"
                )

        # Check for antimeridian crossing
        for i in range(1, len(trackpoints)):
            lon_diff = abs(
                trackpoints[i]["longitude"] - trackpoints[i - 1]["longitude"]
            )
            if lon_diff > 180.0:
                raise RouteValidationError(
                    f"Route crosses antimeridian between points {i-1} and {i} "
                    f"(longitude jump: {lon_diff:.3f}°)"
                )

    def __len__(self) -> int:
        """Return number of trackpoints in route."""
        return len(self.trackpoints)

    def __getitem__(self, index):
        """Allow indexing into trackpoints."""
        return self.trackpoints[index]

    def __iter__(self):
        """Allow iteration over trackpoints."""
        return iter(self.trackpoints)


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
