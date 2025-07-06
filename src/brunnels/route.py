#!/usr/bin/env python3
"""
Route data model for brunnel analysis.
"""

from typing import Tuple, List, TextIO, Dict
import logging
import math
from math import cos, radians
import argparse
import gpxpy
import gpxpy.gpx
from shapely.geometry.base import BaseGeometry
from shapely.geometry import LineString, Point

from .brunnel import Brunnel, BrunnelType, ExclusionReason
from .overpass import query_overpass_brunnels
from .geometry import (
    Position,
    coords_to_polyline,
    create_transverse_mercator_projection,
)

logger = logging.getLogger(__name__)


class Route:
    """Represents a GPX route with memoized geometric operations."""

    def __init__(self, coords: List[Position]):
        """Initializes a Route object.

        Args:
            coords: A list of Position objects representing the route's geometry.

        Raises:
            ValueError: If coords is empty or has fewer than two coordinates.
        """
        if not coords:
            raise ValueError("Route coordinates cannot be empty")
        if len(coords) < 2:
            raise ValueError("Route must have at least two coordinates")

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

        """

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
        Calculates the unbuffered bounding box for the route.

        This internal method determines the minimum and maximum latitude and longitude
        for the route's coordinates. The result is stored and used as the basis
        for the public `get_bbox` method, which can then apply a buffer.

        Returns:
            A tuple (south, west, north, east) representing the bounding box
            in decimal degrees, with no buffer applied.
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

    @staticmethod
    def _get_nearby_brunnels(brunnels: Dict[str, Brunnel]) -> List[Brunnel]:
        """Get brunnels that are nearby and eligible for overlap exclusion, sorted by route span."""
        nearby = [
            b
            for b in brunnels.values()
            if b.is_representative()
            and b.get_route_span() is not None
            and b.exclusion_reason == ExclusionReason.NONE
        ]

        # Sort by route span start distance for consistent processing
        return sorted(nearby, key=lambda b: b.get_route_span().start_distance)  # type: ignore[union-attr]

    @staticmethod
    def _find_overlap_groups(nearby_brunnels: List[Brunnel]) -> List[List[Brunnel]]:
        """Find groups of overlapping brunnels from pre-sorted list."""
        overlap_groups = []
        i = 0

        while i < len(nearby_brunnels):
            current_group = [nearby_brunnels[i]]
            j = i + 1

            # Find all contiguous overlapping brunnels
            while j < len(nearby_brunnels):
                if any(
                    brunnel_in_group.overlaps_with(nearby_brunnels[j])
                    for brunnel_in_group in current_group
                ):
                    current_group.append(nearby_brunnels[j])
                    j += 1
                else:
                    break

            # Only add groups with more than one brunnel
            if len(current_group) > 1:
                overlap_groups.append(current_group)

            i = j if j > i + 1 else i + 1

        return overlap_groups

    def _process_overlap_group(self, group: List[Brunnel]) -> None:
        """Process a single overlap group, keeping the nearest and excluding others."""
        logger.debug(f"Processing overlap group with {len(group)} brunnels")

        # Assign the same overlap_group list to all brunnels in this group
        for brunnel in group:
            brunnel.overlap_group = group

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

        # Keep the closest, exclude the rest
        closest_brunnel, closest_distance = brunnel_distances[0]
        logger.debug(
            f"  Keeping closest: {closest_brunnel.get_short_description()} (distance: {closest_distance:.3f}km)"
        )

        for brunnel, distance in brunnel_distances[1:]:
            brunnel.exclusion_reason = ExclusionReason.ALTERNATIVE
            logger.debug(
                f"  Excluded: {brunnel.get_short_description()} (distance: {distance:.3f}km, reason: {brunnel.exclusion_reason})"
            )

    def exclude_overlapping_brunnels(
        self,
        brunnels: Dict[str, Brunnel],
    ) -> None:
        """
        Exclude overlapping brunnels, keeping only the nearest one for each overlapping group.
        Supports both regular and compound brunnels.

        Args:
            brunnels: Dictionary of Brunnel objects to exclude (modified in-place)
        """
        if not self.coords or not brunnels:
            return

        nearby_brunnels = self._get_nearby_brunnels(brunnels)
        if len(nearby_brunnels) < 2:
            return

        overlap_groups = self._find_overlap_groups(nearby_brunnels)
        if not overlap_groups:
            logger.debug("No overlapping brunnels found")
            return

        # Process each overlap group
        for group in overlap_groups:
            self._process_overlap_group(group)

        # Calculate total excluded for debug logging
        total_excluded = sum(len(group) - 1 for group in overlap_groups)
        logger.debug(
            f"Excluded {total_excluded} overlapping brunnels, keeping nearest in each group"
        )

    def _update_incremental_bbox(
        self, min_lat: float, max_lat: float, min_lon: float, max_lon: float, coord
    ) -> Tuple[float, float, float, float]:
        """
        Update bounding box incrementally by adding a new coordinate.

        Leverages the fact that when adding a coordinate, at least one corner
        of the bounding box remains unchanged, avoiding expensive recalculation.

        Args:
            min_lat, max_lat, min_lon, max_lon: Current bounding box
            coord: New coordinate to include

        Returns:
            Updated (min_lat, max_lat, min_lon, max_lon) tuple
        """
        new_lat = coord.latitude
        new_lon = coord.longitude

        # Update only the bounds that need to change
        if new_lat < min_lat:
            min_lat = new_lat
        elif new_lat > max_lat:
            max_lat = new_lat

        if new_lon < min_lon:
            min_lon = new_lon
        elif new_lon > max_lon:
            max_lon = new_lon

        return min_lat, max_lat, min_lon, max_lon

    def _chunk_route_for_queries(
        self, buffer_meters: float = 10.0
    ) -> List[Tuple[int, int, Tuple[float, float, float, float]]]:
        """
        Break route into chunks for separate Overpass queries based on bounding box size.

        Args:
            buffer_meters: Buffer around each chunk in meters

        Returns:
            List of (start_idx, end_idx, bbox) tuples for each chunk
        """
        # Route constructor guarantees coords exist and len >= 2

        # Maximum bounding box size in square degrees
        # Roughly equivalent to 50,000 km² at equator (50000 / 111² ≈ 4.06)
        MAX_DEGREES_SQUARED = 4.0

        chunks = []
        start_idx = 0
        cumulative_distance = 0.0

        # Initialize bounding box with first coordinate
        first_coord = self.coords[0]
        min_lat = max_lat = first_coord.latitude
        min_lon = max_lon = first_coord.longitude

        for i in range(1, len(self.coords)):
            prev_coord = self.coords[i - 1]
            curr_coord = self.coords[i]

            # Calculate distance for logging
            lat1, lon1 = math.radians(prev_coord.latitude), math.radians(
                prev_coord.longitude
            )
            lat2, lon2 = math.radians(curr_coord.latitude), math.radians(
                curr_coord.longitude
            )

            dlat = lat2 - lat1
            dlon = lon2 - lon1
            a = (
                math.sin(dlat / 2) ** 2
                + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
            )
            distance = 2 * 6371000 * math.asin(math.sqrt(a))  # Earth radius in meters
            cumulative_distance += distance

            # Update bounding box incrementally (much faster than recalculating)
            min_lat, max_lat, min_lon, max_lon = self._update_incremental_bbox(
                min_lat, max_lat, min_lon, max_lon, curr_coord
            )

            # Fast bounding box size check using degrees
            lat_diff = max_lat - min_lat
            lon_diff = max_lon - min_lon
            degrees_squared = lat_diff * lon_diff

            # Create chunk when we exceed size threshold or reach the end
            if degrees_squared >= MAX_DEGREES_SQUARED or i == len(self.coords) - 1:
                # Add buffer in degrees (approximate)
                avg_lat = (min_lat + max_lat) / 2
                lat_buffer = buffer_meters / 111000.0
                lon_buffer = buffer_meters / (
                    111000.0 * abs(math.cos(math.radians(avg_lat)))
                )

                bbox = (
                    max(-90.0, min_lat - lat_buffer),  # south
                    max(-180.0, min_lon - lon_buffer),  # west
                    min(90.0, max_lat + lat_buffer),  # north
                    min(180.0, max_lon + lon_buffer),  # east
                )

                chunks.append((start_idx, i, bbox))

                # Calculate approximate area for logging
                approx_area_sq_km = degrees_squared * 111.0 * 111.0
                logger.debug(
                    f"Chunk {len(chunks)}: points {start_idx}-{i} "
                    f"({cumulative_distance/1000:.1f}km), "
                    f"area: {approx_area_sq_km:.1f} sq km, "
                    f"bbox: {bbox[0]:.3f},{bbox[1]:.3f},"
                    f"{bbox[2]:.3f},{bbox[3]:.3f}"
                )

                # Start next chunk and reset bounding box to current coordinate
                start_idx = i
                cumulative_distance = 0.0
                min_lat = max_lat = curr_coord.latitude
                min_lon = max_lon = curr_coord.longitude

        return chunks

    def find_brunnels(self, args: argparse.Namespace) -> Dict[str, Brunnel]:
        """
        Find all bridges and tunnels near this route and check for containment
        within route buffer. For long routes, breaks into chunks to avoid large
        bounding box queries.

        Args:
            args: argparse.Namespace object containing all settings

        Returns:
            Dictionary of Brunnel objects found near the route, with containment
            status set
        """

        # Check if route is long enough to need chunking
        route_length_km = self.linestring.length / 1000.0
        max_chunk_area_sq_km = 50000.0

        if route_length_km <= 500.0:  # Still use distance for very short routes
            # Short route - use single query
            return self._find_brunnels_single_query(args)
        else:
            # Long route - use area-based chunked queries
            return self._find_brunnels_chunked_queries(args, max_chunk_area_sq_km)

    def _find_brunnels_single_query(
        self, args: argparse.Namespace
    ) -> Dict[str, Brunnel]:
        """Find brunnels using a single Overpass query for short routes."""
        bbox = self.get_bbox(args.query_buffer)

        # Calculate and log query area before API call
        south, west, north, east = bbox
        lat_diff = north - south
        lon_diff = east - west
        avg_lat = (north + south) / 2
        lat_km = lat_diff * 111.0
        lon_km = lon_diff * 111.0 * abs(math.cos(math.radians(avg_lat)))
        area_sq_km = lat_km * lon_km

        logger.debug(
            f"Querying Overpass API for bridges and tunnels in "
            f"{area_sq_km:.1f} sq km area..."
        )

        # Get separated bridge and tunnel data
        raw_bridges, raw_tunnels = query_overpass_brunnels(bbox, args)

        return self._process_raw_brunnel_data(raw_bridges, raw_tunnels)

    def _find_brunnels_chunked_queries(
        self, args: argparse.Namespace, max_area_sq_km: float
    ) -> Dict[str, Brunnel]:
        """Find brunnels using multiple chunked Overpass queries for long routes."""
        chunks = self._chunk_route_for_queries(args.query_buffer)

        logger.info(
            f"Long route ({self.linestring.length/1000:.1f}km) - "
            f"breaking into {len(chunks)} chunks for Overpass queries"
        )

        all_raw_bridges = []
        all_raw_tunnels = []
        total_area_sq_km = 0.0

        for i, (start_idx, end_idx, bbox) in enumerate(chunks):
            # Calculate chunk area for logging
            south, west, north, east = bbox
            lat_diff = north - south
            lon_diff = east - west
            avg_lat = (north + south) / 2
            lat_km = lat_diff * 111.0
            lon_km = lon_diff * 111.0 * abs(math.cos(math.radians(avg_lat)))
            area_sq_km = lat_km * lon_km
            total_area_sq_km += area_sq_km

            logger.debug(
                f"Chunk {i+1}/{len(chunks)}: querying {area_sq_km:.1f} sq km area "
                f"(points {start_idx}-{end_idx})"
            )

            # Query this chunk
            raw_bridges, raw_tunnels = query_overpass_brunnels(bbox, args)
            all_raw_bridges.extend(raw_bridges)
            all_raw_tunnels.extend(raw_tunnels)

        logger.debug(
            f"Completed {len(chunks)} chunked queries covering {total_area_sq_km:.1f} sq km total"
        )

        # Merge results by OSM ID to remove duplicates
        bridges_by_id = {way["id"]: way for way in all_raw_bridges}
        tunnels_by_id = {way["id"]: way for way in all_raw_tunnels}

        merged_bridges = list(bridges_by_id.values())
        merged_tunnels = list(tunnels_by_id.values())

        logger.debug(
            f"Merged results: {len(merged_bridges)} unique bridges, "
            f"{len(merged_tunnels)} unique tunnels "
            f"(removed {len(all_raw_bridges) - len(merged_bridges)} duplicate bridges, "
            f"{len(all_raw_tunnels) - len(merged_tunnels)} duplicate tunnels)"
        )

        return self._process_raw_brunnel_data(merged_bridges, merged_tunnels)

    def _process_raw_brunnel_data(
        self, raw_bridges: List[Dict], raw_tunnels: List[Dict]
    ) -> Dict[str, Brunnel]:
        """Process raw bridge and tunnel data into Brunnel objects."""
        brunnels = {}

        # Process bridges
        for way_data in raw_bridges:
            try:
                brunnel = Brunnel.from_overpass_data(
                    way_data, BrunnelType.BRIDGE, self.projection
                )
                brunnels[brunnel.get_id()] = brunnel
            except (KeyError, ValueError) as e:
                logger.warning(f"Failed to parse bridge way: {e}")
                continue

        # Process tunnels
        for way_data in raw_tunnels:
            try:
                brunnel = Brunnel.from_overpass_data(
                    way_data, BrunnelType.TUNNEL, self.projection
                )
                brunnels[brunnel.get_id()] = brunnel
            except (KeyError, ValueError) as e:
                logger.warning(f"Failed to parse tunnel way: {e}")
                continue

        return brunnels

    def average_distance_to_brunnel(self, brunnel: Brunnel) -> float:
        """
        Calculate the average distance from all points in a brunnel to the closest points on this route.

        The distance is measured in projected coordinates (typically meters) and then
        averaged and converted to kilometers.

        Args:
            brunnel: Brunnel object to calculate distances for.

        Returns:
            float: Average distance in kilometers.
        """

        points = [Point(coord) for coord in brunnel.linestring.coords]

        total_distance = 0.0

        for point in points:
            total_distance += point.distance(self.linestring)

        return total_distance / len(points) / 1000.0  # Convert to kilometers

    def euclidean_to_3d_haversine_distance(self, euclidean_distance: float) -> float:
        """
        Convert a Euclidean distance along the route to a 3D Haversine distance.

        Uses precomputed cumulative distances with binary search for efficiency.
        Includes elevation changes using the Pythagorean theorem.

        Args:
            euclidean_distance: Distance in meters along the route in projected coordinates

        Returns:
            Corresponding 3D Haversine distance in meters
        """
        if not hasattr(self, "_cumulative_euclidean_distances"):
            self._precompute_cumulative_distances()

        # Handle edge cases
        if euclidean_distance <= 0:
            return 0.0
        if euclidean_distance >= self._cumulative_euclidean_distances[-1]:
            return self._cumulative_3d_haversine_distances[-1]

        # Binary search to find the largest cumulative distance less than the given distance
        left, right = 0, len(self._cumulative_euclidean_distances) - 1
        while left < right:
            mid = (left + right + 1) // 2
            if self._cumulative_euclidean_distances[mid] <= euclidean_distance:
                left = mid
            else:
                right = mid - 1

        # left is now the index of the largest cumulative distance <= euclidean_distance
        segment_idx = left

        # If we're exactly at a point, return the cumulative distance
        if euclidean_distance == self._cumulative_euclidean_distances[segment_idx]:
            return self._cumulative_3d_haversine_distances[segment_idx]

        # Interpolate within the segment
        if segment_idx == len(self._cumulative_euclidean_distances) - 1:
            # We're at the end, just return the last cumulative distance
            return self._cumulative_3d_haversine_distances[segment_idx]

        # Calculate interpolation factors
        segment_start_euclidean = self._cumulative_euclidean_distances[segment_idx]
        segment_end_euclidean = self._cumulative_euclidean_distances[segment_idx + 1]
        segment_start_3d = self._cumulative_3d_haversine_distances[segment_idx]
        segment_end_3d = self._cumulative_3d_haversine_distances[segment_idx + 1]

        # Linear interpolation
        t = (euclidean_distance - segment_start_euclidean) / (
            segment_end_euclidean - segment_start_euclidean
        )
        return segment_start_3d + t * (segment_end_3d - segment_start_3d)

    def _precompute_cumulative_distances(self) -> None:
        """Precompute cumulative Euclidean and 3D Haversine distances."""
        if len(self.coords) < 2:
            self._cumulative_euclidean_distances = [0.0]
            self._cumulative_3d_haversine_distances = [0.0]
            return

        euclidean_distances = [0.0]
        haversine_distances = [0.0]

        cumulative_euclidean = 0.0
        cumulative_haversine = 0.0

        # Get projected coordinates for Euclidean distance calculation
        projected_coords = list(self.linestring.coords)

        for i in range(1, len(self.coords)):
            # Calculate Euclidean distance in projected coordinates
            p1 = projected_coords[i - 1]
            p2 = projected_coords[i]
            euclidean_segment = math.sqrt((p2[0] - p1[0]) ** 2 + (p2[1] - p1[1]) ** 2)

            # Calculate 3D Haversine distance
            coord1 = self.coords[i - 1]
            coord2 = self.coords[i]
            haversine_segment = self._calculate_3d_haversine_distance(coord1, coord2)

            cumulative_euclidean += euclidean_segment
            cumulative_haversine += haversine_segment

            euclidean_distances.append(cumulative_euclidean)
            haversine_distances.append(cumulative_haversine)

        self._cumulative_euclidean_distances = euclidean_distances
        self._cumulative_3d_haversine_distances = haversine_distances

    def _calculate_3d_haversine_distance(
        self, coord1: Position, coord2: Position
    ) -> float:
        """
        Calculate 3D Haversine distance between two coordinates.

        Uses Haversine formula for great circle distance, then applies
        Pythagorean theorem to account for elevation difference.
        """
        # Haversine formula for great circle distance
        lat1, lon1 = math.radians(coord1.latitude), math.radians(coord1.longitude)
        lat2, lon2 = math.radians(coord2.latitude), math.radians(coord2.longitude)

        dlat = lat2 - lat1
        dlon = lon2 - lon1

        a = (
            math.sin(dlat / 2) ** 2
            + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        )

        # Earth radius in meters
        earth_radius = 6371000.0
        haversine_distance = 2 * earth_radius * math.asin(math.sqrt(a))

        # Add elevation component if available
        if coord1.elevation is not None and coord2.elevation is not None:
            elevation_diff = coord2.elevation - coord1.elevation
            # 3D distance using Pythagorean theorem
            return math.sqrt(haversine_distance**2 + elevation_diff**2)

        return haversine_distance

    @classmethod
    def from_gpx(cls, file_input: TextIO) -> "Route":
        """
        Parse GPX file and concatenate all tracks/segments into a single route.

        Args:
            file_input: File-like object containing GPX data

        Returns:
            Route object representing the concatenated route

        Raises:
            RuntimeError: If the route crosses the antimeridian or approaches poles.
            gpxpy.gpx.GPXException: If GPX file is malformed.
        """
        gpx_data = gpxpy.parse(file_input)

        coords_data = []

        # Extract all track points from all tracks and segments
        for track in gpx_data.tracks:
            for segment in track.segments:
                for point in segment.points:
                    coords_data.append(
                        Position(
                            latitude=point.latitude,
                            longitude=point.longitude,
                            elevation=point.elevation,
                        )
                    )

        # Note: The __init__ method will raise ValueError if coords_data is empty or has less than 2 points.
        route = cls(coords_data)

        logger.debug(f"Parsed {len(route.coords)} track points from GPX file")

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
            RuntimeError: If route fails validation (e.g., antimeridian crossing, polar proximity).
            FileNotFoundError: If file doesn't exist.
            PermissionError: If file can't be read.
            gpxpy.gpx.GPXException: If GPX file is malformed.
        """
        logger.debug(f"Reading GPX file: {filename}")
        with open(filename, "r", encoding="utf-8") as f:
            return cls.from_gpx(f)

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

    def exclude_misaligned_brunnels(
        self,
        brunnels: Dict[str, Brunnel],
        bearing_tolerance_degrees: float,
    ) -> None:
        """
        Excludes a list of brunnels by their alignment with the route.

        Args:

            bearing_tolerance_degrees: Bearing alignment tolerance in degrees.
            self: The Route instance.

        """
        misaligned_count = 0

        for brunnel in brunnels.values():

            if (
                brunnel.exclusion_reason == ExclusionReason.NONE
                and not brunnel.is_aligned_with_route(self, bearing_tolerance_degrees)
            ):
                brunnel.exclusion_reason = ExclusionReason.MISALIGNED
                misaligned_count += 1

        if misaligned_count > 0:
            logger.debug(
                f"Excluded {misaligned_count} brunnels out of {len(brunnels)} "
                f"contained brunnels due to bearing misalignment (tolerance: {bearing_tolerance_degrees}°)"
            )

    def calculate_route_spans(self, brunnels: Dict[str, Brunnel]) -> None:
        """
        Calculate the route span for each included brunnel.
        """
        for brunnel in brunnels.values():
            if brunnel.exclusion_reason == ExclusionReason.NONE:
                brunnel.calculate_route_span(self)
