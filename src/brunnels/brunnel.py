#!/usr/bin/env python3
"""Data structures for representing bridges and tunnels (brunnels)."""

from typing import Optional, List, Dict, Any, Set, NamedTuple
from collections import defaultdict, deque
from enum import Enum
import logging
from shapely import Point
from shapely.geometry import LineString
import pyproj

from .geometry_utils import Position
from .geometry_utils import (
    bearing,
    bearings_aligned,
)
from .shapely_utils import (
    coords_to_polyline,
    find_closest_segments,
)

logger = logging.getLogger(__name__)


class BrunnelType(Enum):
    """Enumeration for brunnel (bridge/tunnel) types."""

    BRIDGE = "bridge"
    TUNNEL = "tunnel"

    def __str__(self) -> str:
        return self.value.capitalize()


class FilterReason(Enum):
    """Enumeration for brunnel filtering reasons."""

    NONE = "none"
    NOT_CONTAINED = "outwith_route_buffer"
    UNALIGNED = "not_aligned_with_route"
    NOT_NEAREST = "not_nearest_among_overlapping_brunnels"

    def __str__(self) -> str:
        return self.value


class RouteSpan(NamedTuple):
    """Information about where a brunnel spans along a route."""

    start_distance: float  # Distance from route start where brunnel begins
    end_distance: float  # Distance from route start where brunnel ends


class Brunnel:
    """A single bridge or tunnel way from OpenStreetMap."""

    def __init__(
        self,
        coords: List[Position],
        metadata: Dict[str, Any],
        brunnel_type: BrunnelType,
        filter_reason: FilterReason = FilterReason.NONE,
        route_span: Optional[RouteSpan] = None,
        compound_group: Optional[List["Brunnel"]] = None,
        projection: Optional[pyproj.Proj] = None,
    ):
        """Initializes a Brunnel object.

        Args:
            coords: A list of Position objects representing the brunnel's geometry.
            metadata: A dictionary containing metadata from OpenStreetMap.
            brunnel_type: The type of the brunnel (BRIDGE or TUNNEL).
            filter_reason: The reason why this brunnel might be filtered out.
            route_span: A RouteSpan object indicating where the brunnel intersects with a route.
            compound_group: A list of other Brunnel objects if this is part of a compound structure.
            projection: A pyproj.Proj object for coordinate transformations.

        Raises:
            ValueError: If coords is empty or has insufficient coordinates.
        """
        self.coords = coords
        self.metadata = metadata
        self.brunnel_type = brunnel_type
        self.filter_reason = filter_reason
        self.route_span = route_span
        self.compound_group = compound_group
        self.projection = projection
        if not coords:
            raise ValueError(f"{self.get_short_description()} has no coordinates")
        if len(coords) < 2:
            raise ValueError(
                f"{self.get_short_description()} has insufficient coordinates"
            )
        coord_tuples = [(pos.longitude, pos.latitude) for pos in self.coords]
        self.linestring: LineString = coords_to_polyline(coord_tuples, self.projection)

    def is_representative(self) -> bool:
        """
        Checks if this brunnel is the representative of its compound group.

        If the brunnel is not part of a compound group, it is always representative.
        Otherwise, only the first brunnel in the sorted compound_group list is considered representative.

        Returns:
            bool: True if this brunnel is representative, False otherwise.
        """
        if self.compound_group is None:
            return True
        compound_group = self.compound_group
        return compound_group.index(self) == 0

    def get_id(self) -> str:
        """Get a string identifier for this brunnel.

        For a simple brunnel, this is usually its OSM ID.
        For a compound brunnel, it's a semicolon-separated string of the OSM IDs
        of all its component brunnels.

        Returns:
            str: The identifier string.
        """
        if self.compound_group is not None:
            return ";".join(
                str(component.metadata.get("id", "unknown"))
                for component in self.compound_group
            )
        return str(self.metadata.get("id", "unknown"))

    def get_display_name(self) -> str:
        """Get the display name for this brunnel.

        Retrieves the 'name' tag from OSM metadata. If no 'name' tag exists,
        returns "unnamed".

        Returns:
            str: The OSM name or "unnamed".
        """
        if self.compound_group is not None:
            # For compound brunnels, use the name of the first named component
            for component in self.compound_group:
                if "name" in component.metadata["tags"]:
                    return component.metadata["tags"]["name"]
            logging.debug("No names in compound group")
            return "unnamed"
        return self.metadata["tags"].get("name", "unnamed")

    def get_short_description(self) -> str:
        """Get a short, human-readable description for logging.

        Includes the brunnel type, display name, ID, and segment count for compound brunnels.

        Returns:
            str: A short descriptive string.
        """
        brunnel_type = self.brunnel_type.value.capitalize()
        name = self.get_display_name()
        if self.compound_group is not None:
            component_count = len(self.compound_group)
            return f"Compound {brunnel_type}: {name} ({self.get_id()}) [{component_count} segments]"
        return f"{brunnel_type}: {name} ({self.get_id()})"

    def get_log_description(self) -> str:
        """Get a standardized description for logging, including route span information.

        Combines the short description with formatted route span distances if available.

        Returns:
            str: A descriptive string for logging purposes.
        """
        route_span = self.get_route_span()
        if route_span is not None:
            span_info = f"{route_span.start_distance:.2f}-{route_span.end_distance:.2f} km (length: {route_span.end_distance - route_span.start_distance:.2f} km)"
            return f"{self.get_short_description()} {span_info}"
        else:
            return f"{self.get_short_description()} (no route span)"

    def get_route_span(self) -> Optional[RouteSpan]:
        """
        Get the RouteSpan for this brunnel.

        For a simple brunnel, this is its own route_span.
        For a compound brunnel, it's calculated from the route_spans of its
        first and last components.

        Returns:
            Optional[RouteSpan]: The route span, or None if not calculated.

        Raises:
            ValueError: If a compound brunnel has a component without a route_span.
        """
        if self.compound_group is not None and len(self.compound_group) > 0:
            first_component = self.compound_group[0]
            last_component = self.compound_group[-1]
            if first_component.route_span is None or last_component.route_span is None:
                raise ValueError(
                    f"Compound brunnel {self.get_id()} has component without route_span"
                )
            return RouteSpan(
                first_component.route_span.start_distance,
                last_component.route_span.end_distance,
            )
        return self.route_span

    def overlaps_with(self, other: "Brunnel") -> bool:
        """
        Check if this brunnel's route span overlaps with another brunnel's route span.

        Args:
            other: Another Brunnel object

        Returns:
            True if their route spans overlap, False otherwise.
            Returns False if either brunnel does not have a route_span.
        """
        if self.route_span is None or other.route_span is None:
            return False
        return (
            self.route_span.start_distance <= other.route_span.end_distance
            and other.route_span.start_distance <= self.route_span.end_distance
        )

    def is_contained_by(self, route_geometry) -> bool:
        """
        Check if this brunnel is completely contained within a route geometry.

        Args:
            route_geometry: Shapely geometry object representing the buffered route polygon

        Returns:
            True if the route geometry completely contains this brunnel, False otherwise
        """

        return route_geometry.contains(self.linestring)

    def calculate_route_span(self, route) -> None:
        """
        Calculate the span of this brunnel along the route.

        Args:
            route: Route object representing the route
        """
        min_distance = float("inf")
        max_distance = -float("inf")

        points = [Point(coord) for coord in self.linestring.coords]
        # Find the closest route point for each brunnel coordinate
        for point in points:
            distance = route.linestring.project(point) / 1000.0  # Convert to kilometers

            min_distance = min(min_distance, distance)
            max_distance = max(max_distance, distance)

        self.route_span = RouteSpan(min_distance, max_distance)

    def is_aligned_with_route(self, route, tolerance_degrees: float) -> bool:
        """
        Check if this brunnel's bearing is aligned with the route at their closest point.

        Args:
            route: Route object representing the route
            tolerance_degrees: Allowed bearing deviation in degrees

        Returns:
            True if brunnel is aligned with route within tolerance, False otherwise
        """

        # Find closest segments between brunnel and route
        brunnel_index, route_index = find_closest_segments(
            self.linestring, route.linestring
        )

        # Extract segment coordinates
        brunnel_start = self.coords[brunnel_index]
        brunnel_end = self.coords[brunnel_index + 1]
        route_start = route.coords[route_index]
        route_end = route.coords[route_index + 1]

        # Calculate bearings for both segments
        brunnel_bearing = bearing(brunnel_start, brunnel_end)
        route_bearing = bearing(route_start, route_end)

        # Check if bearings are aligned
        aligned = bearings_aligned(brunnel_bearing, route_bearing, tolerance_degrees)

        logger.debug(
            f"{self.get_short_description()}: brunnel_bearing={brunnel_bearing:.1f}°, route_bearing={route_bearing:.1f}°, aligned={aligned} (tolerance={tolerance_degrees}°)"
        )

        return aligned

    @classmethod
    def from_overpass_data(
        cls,
        way_data: Dict[str, Any],
        brunnel_type: BrunnelType,
        projection: Optional[pyproj.Proj] = None,
    ) -> "Brunnel":
        """
        Parse a single way from Overpass response into Brunnel object.

        Args:
            way_data: Raw way data from Overpass API
            brunnel_type: Type of brunnel (BRIDGE or TUNNEL)
            projection: Optional projection for coordinate transformation

        Returns:
            Brunnel object
        """
        # Extract coordinates from geometry
        coords = []
        if "geometry" in way_data:
            for node in way_data["geometry"]:
                coords.append(Position(latitude=node["lat"], longitude=node["lon"]))

        return cls(
            coords=coords,
            metadata=way_data,
            brunnel_type=brunnel_type,
            projection=projection,
        )


def find_compound_brunnels(brunnels: Dict[str, Brunnel]) -> None:
    """
    Identify connected components of brunnels and mark compound groups.

    This function analyzes the graph formed by brunnels sharing nodes and identifies
    connected components. For components with more than one way, it constructs a compound group
    to mark them as part of the same logical structure.

    Args:
        brunnels: Dictionary of Brunnel objects to analyze
    """
    # Step 1: Build edges dictionary mapping node IDs to collections of way IDs
    edges: Dict[str, Set[str]] = defaultdict(set)
    way_ids = []

    for brunnel in brunnels.values():
        # Only process brunnels that are not filtered
        if brunnel.filter_reason != FilterReason.NONE:
            continue

        way_id = brunnel.get_id()
        way_ids.append(way_id)

        # Get nodes from metadata
        nodes = brunnel.metadata.get("nodes", [])

        # Add this way ID to the edge list for each of its nodes
        for node_id in nodes:
            edges[node_id].add(way_id)

    # Step 2: Find connected components using breadth-first search
    visited_ways: Set[str] = set()
    connected_components: List[Set[str]] = []

    # Process each way that hasn't been visited
    for way_id in way_ids:
        if way_id in visited_ways:
            continue

        # Start BFS from this way to find its connected component
        component: Set[str] = set()
        queue: deque[str] = deque([way_id])

        while queue:
            current_way = queue.popleft()

            if current_way in visited_ways:
                continue

            visited_ways.add(current_way)
            component.add(current_way)

            # Find all ways connected to this way through shared nodes
            brunnel = brunnels[current_way]
            current_nodes = brunnel.metadata.get("nodes", [])

            for node_id in current_nodes:
                # Find all other ways that share this node
                connected_ways = edges[node_id]
                for connected_way in connected_ways:
                    if connected_way not in visited_ways:
                        queue.append(connected_way)

        connected_components.append(component)

    # Step 3: Mark compound groups
    for component in connected_components:
        # Only mark components with more than one way as compound groups
        if len(component) > 1:
            # Add compound_group to all brunnels in this component
            logger.debug(
                f"Marking compound group with {len(component)} ways: {', '.join(component)}"
            )
            compound_group = [brunnels[way_id] for way_id in component]
            # Sort by start distance for consistent ordering
            compound_group.sort(
                key=lambda b: b.route_span.start_distance if b.route_span else 0.0
            )
            for way_id in component:
                brunnel = brunnels[way_id]
                brunnel.compound_group = compound_group
