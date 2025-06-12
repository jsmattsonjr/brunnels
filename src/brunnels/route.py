#!/usr/bin/env python3
"""
Route data model for brunnel analysis.
"""

from typing import Optional, Tuple, List, TextIO, Dict, Any
from dataclasses import dataclass, field
import logging
import math
from math import cos, radians
import gpxpy
import gpxpy.gpx

from .geometry import Position, Geometry
from .config import BrunnelsConfig
from .brunnel import Brunnel, BrunnelType, FilterReason
from .overpass import query_overpass_brunnels

logger = logging.getLogger(__name__)


class UnsupportedRouteError(Exception):
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
            self._bbox = self._calculate_bbox()

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

    def _calculate_bbox(self) -> Tuple[float, float, float, float]:
        """
        Calculate bounding box for route, always with a 0 buffer.

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
        brunnels: Dict[str, Brunnel],
        route_buffer: float,
        bearing_tolerance_degrees: float,
    ) -> None:
        """
        Check which brunnels are completely contained within the buffered route and aligned with route bearing.
        Updates their containment status and calculates route spans for contained brunnels.

        Args:
            brunnels: Dictionary of Brunnel objects to check (modified in-place)
            route_buffer: Buffer distance in meters to apply around the route (minimum: 1.0)
            bearing_tolerance_degrees: Bearing alignment tolerance in degrees
        """
        if not self.trackpoints:
            logger.warning("Cannot find contained brunnels for empty route")
            return

        # Ensure minimum buffer for containment analysis
        if route_buffer < 1.0:
            logger.warning(
                f"Minimum buffer of 1.0m required for containment analysis, using 1.0m instead of {route_buffer}m."
            )
            route_buffer = 1.0

        # 1. Calculate buffered route geometry
        route_geometry = self._calculate_buffered_route_geometry(route_buffer)

        if route_geometry is None:
            logger.warning(
                "Could not calculate buffered route geometry. "
                "Aborting brunnel containment analysis."
            )
            # Mark all brunnels as not contained if geometry calculation fails
            for brunnel in brunnels.values():
                if brunnel.filter_reason == FilterReason.NONE:
                    brunnel.filter_reason = FilterReason.NOT_CONTAINED
            return

        # 2. Find brunnels within this geometry
        # This step updates filter_reason for brunnels not in geometry.
        contained_brunnels_list = self._find_brunnels_in_geometry(
            route_geometry, brunnels
        )

        logger.debug(
            f"Found {len(contained_brunnels_list)} brunnels initially contained within the route geometry "
            f"(buffer: {route_buffer}m)."
        )

        # 3. Filter contained brunnels by alignment and calculate route spans
        # This step updates filter_reason for unaligned brunnels and sets route_span.
        aligned_brunnels_list = self._filter_brunnels_by_alignment(
            contained_brunnels_list, bearing_tolerance_degrees
        )

        final_count = len(aligned_brunnels_list)

        # To accurately report "out of X total brunnels that were candidates",
        # we need to know how many brunnels started with FilterReason.NONE.
        # The current structure modifies brunnels in place.
        # For simplicity, we'll log based on the number of brunnels passed to this function.
        # A more complex approach would be to count brunnels with FilterReason.NONE at the start of this method.

        logger.info( # Changed to INFO for final summary
            f"Found {final_count} brunnels completely contained and aligned within the route buffer "
            f"(route buffer: {route_buffer}m, bearing tolerance: {bearing_tolerance_degrees}°)."
        )
        # The detailed count of unaligned brunnels is logged within _filter_brunnels_by_alignment.

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
        if not self.trackpoints or not brunnels:
            return

        # Only consider contained brunnels with route spans
        contained_brunnels = [
            b
            for b in brunnels.values()
            if b.is_representative()
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
                        if (
                            brunnel_in_group.route_span is not None
                            and brunnel2.route_span is not None
                            and brunnel_in_group.route_span.overlaps_with(
                                brunnel2.route_span
                            )
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
                filtered += 1

                logger.debug(
                    f"  Filtered: {brunnel.get_short_description()} (distance: {distance:.3f}km, reason: {brunnel.filter_reason})"
                )

        if filtered > 0:
            logger.debug(
                f"Filtered {filtered} overlapping brunnels, keeping nearest in each group"
            )

    def find_brunnels(self, config: BrunnelsConfig) -> Dict[str, Brunnel]:
        """
        Find all bridges and tunnels near this route and check for containment within route buffer.

        Args:
            config: BrunnelsConfig object containing all settings

        Returns:
            List of Brunnel objects found near the route, with containment status set
        """
        if not self.trackpoints:
            logger.warning("Cannot find brunnels for empty route")
            return {}

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

        brunnels = {}
        filtered_count = 0
        for way_data in raw_ways:
            try:
                brunnel = Brunnel.from_overpass_data(way_data)
                # Count filtered brunnels but keep them for visualization
                if brunnel.filter_reason != FilterReason.NONE:
                    filtered_count += 1

                brunnels[brunnel.get_id()] = brunnel
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
        bridges = [b for b in brunnels.values() if b.brunnel_type == BrunnelType.BRIDGE]
        tunnels = [b for b in brunnels.values() if b.brunnel_type == BrunnelType.TUNNEL]
        contained_bridges = [b for b in bridges if b.filter_reason == FilterReason.NONE]
        contained_tunnels = [b for b in tunnels if b.filter_reason == FilterReason.NONE]

        logger.debug(
            f"Found {len(contained_bridges)}/{len(bridges)} contained bridges and {len(contained_tunnels)}/{len(tunnels)} contained tunnels"
        )

        return brunnels

    def average_distance_to_polyline(self, geometry: Geometry) -> float:
        """
        Calculate the average distance from all points in a geometry to the closest points on this route.

        Args:
            geometry: Any Geometry object (Brunnel, CompoundBrunnel, etc.)

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
                _, closest_route_point = self.closest_point_to(geometry_point)
                # Calculate direct distance between geometry point and closest route point
                distance = geometry_point.distance_to(closest_route_point)
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
            segment_distance = prev_point.distance_to(curr_point)
            self.trackpoints[i]["track_distance"] = (
                self.trackpoints[i - 1]["track_distance"] + segment_distance
            )

    def closest_point_to(self: "Route", point: Position) -> Tuple[float, Position]:
        """
        Find the closest point on a route to a given point and return the cumulative distance.

        Args:
            point: Point to find closest route point for

        Returns:
            Tuple of (distance, closest_position) where:
            - distance: Distance from route start to closest point
            - closest_position: Position of closest point on route
        """
        route_positions = self.coordinate_list

        if len(route_positions) < 2:
            raise ValueError(
                "Route must have at least two positions to calculate distance."
            )

        min_distance = float("inf")
        best_distance = 0.0
        best_position = route_positions[0]

        # Check each segment of the route
        for i in range(len(route_positions) - 1):
            seg_start = route_positions[i]
            seg_end = route_positions[i + 1]

            distance, t, closest_point = point.to_line_segment_distance_and_projection(
                seg_start, seg_end
            )

            if distance < min_distance:
                min_distance = distance
                best_position = closest_point

                # Calculate cumulative distance to this point
                best_distance = self.trackpoints[i][
                    "track_distance"
                ] + seg_start.distance_to(best_position)

        return best_distance, best_position

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
            UnsupprtedRouteError: If validation fails
        """
        if not trackpoints:
            return

        # Check for polar proximity (within 5 degrees of poles)
        for i, tp in enumerate(trackpoints):
            if abs(tp["latitude"]) > 85.0:
                raise UnsupportedRouteError(
                    f"Route point {i} at latitude {tp['latitude']:.3f}° is within "
                    f"5 degrees of a pole"
                )

        # Check for antimeridian crossing
        for i in range(1, len(trackpoints)):
            lon_diff = abs(
                trackpoints[i]["longitude"] - trackpoints[i - 1]["longitude"]
            )
            if lon_diff > 180.0:
                raise UnsupportedRouteError(
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

    def _calculate_buffered_route_geometry(
        self, route_buffer: float
    ) -> Optional[Any]:  # Using Any for Shapely geometry for now
        """
        Calculate the buffered Shapely geometry for the route.

        Args:
            route_buffer: Buffer distance in meters.

        Returns:
            Shapely geometry object or None if it could not be created.
        """
        if not self.trackpoints:
            logger.warning(
                "Cannot calculate buffered geometry for empty route, trackpoints are empty"
            )
            return None

        route_line = self.get_linestring()
        if route_line is None:
            logger.warning(
                "Cannot calculate buffered geometry because LineString is None"
            )
            return None

        # Convert buffer from meters to approximate degrees
        # (Similar to find_contained_brunnels)
        # It's important to use a representative latitude for the conversion.
        # Using the latitude of the first trackpoint as a simple approach.
        # A more robust approach might involve averaging latitudes or using the centroid.
        if not self.trackpoints: # Should be caught by the first check, but defensive
            logger.warning("Trackpoints list is empty, cannot determine average latitude.")
            return None

        avg_lat = self.trackpoints[0]["latitude"]
        # 1 degree latitude ≈ 111 km = 111000m
        lat_buffer_deg = route_buffer / 111000.0
        # Longitude conversion depends on latitude
        lon_buffer_deg = route_buffer / (111000.0 * abs(cos(radians(avg_lat))))

        # Use the smaller of the two buffers to be conservative,
        # as buffering is generally isotropic in projected coordinate systems
        # but here we are using geographic coordinates.
        buffer_degrees = min(lat_buffer_deg, lon_buffer_deg)

        if buffer_degrees <= 0:
            logger.warning(
                f"Calculated buffer in degrees is {buffer_degrees:.6f}. "
                "This might lead to unexpected behavior or invalid geometry. "
                "Ensure route_buffer is positive and trackpoints are valid."
            )
            # Depending on desired behavior, could return None or attempt to buffer with a very small positive value.
            # For now, proceed with the calculated (potentially non-positive) buffer.

        try:
            route_geometry = route_line.buffer(buffer_degrees)
        except Exception as e:
            logger.error(f"Error during route_line.buffer operation: {e}")
            return None

        if not route_geometry.is_valid:
            logger.warning(
                "Initial buffered route geometry is invalid. Attempting to fix with buffer(0)."
            )
            try:
                fixed_geometry = route_geometry.buffer(0)
                if fixed_geometry.is_valid:
                    logger.info("Successfully fixed invalid buffered geometry.")
                    return fixed_geometry
                else:
                    logger.warning(
                        "Could not fix invalid buffered geometry after attempting buffer(0). "
                        "The geometry remains invalid."
                    )
                    # Return the still-invalid geometry as per original find_contained_brunnels logic,
                    # or decide to return None if invalid geometry is unacceptable.
                    return fixed_geometry
            except Exception as e:
                logger.warning(
                    f"Exception while trying to fix invalid geometry with buffer(0): {e}"
                )
                # Return the original invalid geometry if fixing fails
                return route_geometry

        return route_geometry

    def _find_brunnels_in_geometry(
        self, route_geometry: Any, brunnels: Dict[str, Brunnel]
    ) -> List[Brunnel]:
        """
        Finds brunnels that are contained within the given route geometry.

        Args:
            route_geometry: The Shapely geometry of the (buffered) route.
            brunnels: A dictionary of Brunnel objects to check.

        Returns:
            A list of Brunnel objects that are contained within the route_geometry
            and were not previously filtered.
        """
        contained_brunnels: List[Brunnel] = []

        if route_geometry is None:
            logger.warning(
                "Route geometry is None, cannot find brunnels in geometry."
            )
            # Set all non-filtered brunnels to NOT_CONTAINED as a precaution
            for brunnel in brunnels.values():
                if brunnel.filter_reason == FilterReason.NONE:
                    brunnel.filter_reason = FilterReason.NOT_CONTAINED
            return contained_brunnels

        for brunnel in brunnels.values():
            # Only check containment for brunnels that weren't filtered by other reasons
            if brunnel.filter_reason == FilterReason.NONE:
                if brunnel.is_contained_by(route_geometry):
                    contained_brunnels.append(brunnel)
                else:
                    # Set filter reason for non-contained brunnels
                    brunnel.filter_reason = FilterReason.NOT_CONTAINED

        logger.debug(
            f"Found {len(contained_brunnels)} brunnels within the route geometry "
            f"out of {sum(1 for b in brunnels.values() if b.filter_reason == FilterReason.NONE)} previously unfiltered brunnels."
        )
        return contained_brunnels

    def _filter_brunnels_by_alignment(
        self,
        contained_brunnels: List[Brunnel],
        bearing_tolerance_degrees: float,
    ) -> List[Brunnel]:
        """
        Filters a list of brunnels by their alignment with the route.
        Calculates route_span for aligned brunnels.

        Args:
            contained_brunnels: A list of Brunnel objects that are already known
                                to be contained within the route buffer.
            bearing_tolerance_degrees: Bearing alignment tolerance in degrees.
            self: The Route instance.

        Returns:
            A list of Brunnel objects that are aligned with the route.
        """
        aligned_brunnels: List[Brunnel] = []
        unaligned_count = 0

        for brunnel in contained_brunnels:
            # Assuming brunnels in contained_brunnels list are candidates for alignment check
            # (i.e., their filter_reason was NONE before this stage, or this check is independent)
            if brunnel.is_aligned_with_route(self, bearing_tolerance_degrees):
                # Calculate route span for aligned, contained brunnels
                brunnel.route_span = brunnel.calculate_route_span(self)
                aligned_brunnels.append(brunnel)
            else:
                # Mark as unaligned
                brunnel.filter_reason = FilterReason.UNALIGNED
                unaligned_count += 1

        if unaligned_count > 0:
            logger.debug(
                f"Filtered {unaligned_count} brunnels out of {len(contained_brunnels)} "
                f"contained brunnels due to bearing misalignment (tolerance: {bearing_tolerance_degrees}°)"
            )

        return aligned_brunnels
