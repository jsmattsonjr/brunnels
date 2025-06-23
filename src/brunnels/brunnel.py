#!/usr/bin/env python3
"""Data structures for representing bridges and tunnels (brunnels)."""

from typing import Optional, List, Dict, Any, Set, NamedTuple, Tuple
from collections import defaultdict, deque
from enum import Enum
import logging
from shapely import Point
from shapely.geometry import LineString
from shapely.ops import substring
import pyproj
import math

from .geometry import (
    Position,
    coords_to_polyline,
)

logger = logging.getLogger(__name__)


class BrunnelType(Enum):
    """Enumeration for brunnel (bridge/tunnel) types."""

    BRIDGE = "bridge"
    TUNNEL = "tunnel"

    def __str__(self) -> str:
        return self.value.capitalize()


class ExclusionReason(Enum):
    """Enumeration for brunnel exclusion reasons."""

    NONE = "none"
    OUTLIER = "outlier"
    MISALIGNED = "misaligned"
    ALTERNATIVE = "alternative"

    def __str__(self) -> str:
        return self.value


class RouteSpan(NamedTuple):
    """Information about where a brunnel spans along a route."""

    start_distance: float  # Distance from route start where brunnel begins (in meters)
    end_distance: float  # Distance from route start where brunnel ends (in meters)


class Brunnel:
    """A single bridge or tunnel way from OpenStreetMap."""

    def __init__(
        self,
        coords: List[Position],
        metadata: Dict[str, Any],
        brunnel_type: BrunnelType,
        exclusion_reason: ExclusionReason = ExclusionReason.NONE,
        route_span: Optional[RouteSpan] = None,
        compound_group: Optional[List["Brunnel"]] = None,
        overlap_group: Optional[List["Brunnel"]] = None,
        projection: Optional[pyproj.Proj] = None,
    ):
        """Initializes a Brunnel object.

        Args:
            coords: A list of Position objects representing the brunnel's geometry.
            metadata: A dictionary containing metadata from OpenStreetMap.
            brunnel_type: The type of the brunnel (BRIDGE or TUNNEL).
            exclusion_reason: The reason why this brunnel might be excluded.
            route_span: A RouteSpan object indicating where the brunnel intersects with a route.
            compound_group: A list of other Brunnel objects if this is part of a compound structure.
            overlap_group: A list of other Brunnel objects if this overlaps with other brunnels.
            projection: A pyproj.Proj object for coordinate transformations.

        Raises:
            ValueError: If coords is empty or has insufficient coordinates.
        """
        self.coords = coords
        self.metadata = metadata
        self.brunnel_type = brunnel_type
        self.exclusion_reason = exclusion_reason
        self.route_span = route_span
        self.compound_group = compound_group
        self.overlap_group = overlap_group
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

        For compound brunnels, collects names from all components (using "<OSM id>" for unnamed
        components). If all names match, returns the common name; otherwise joins names with ';'.
        For simple brunnels, retrieves the 'name' tag from OSM metadata, or returns a formatted
        OSM ID if no name exists.

        Returns:
            str: The OSM name, joined names, or "<OSM {id}>" for unnamed brunnels.
        """
        if self.compound_group is not None:
            names = []
            for component in self.compound_group:
                if "name" in component.metadata["tags"]:
                    names.append(component.metadata["tags"]["name"])
                else:
                    # Use <OSM id> format for unnamed components
                    component_id = component.metadata.get("id", "unknown")
                    names.append(f"<OSM {component_id}>")

            # If all names are the same, return the common name
            if len(set(names)) == 1:
                return names[0]
            # Otherwise, join all names with ';'
            return "; ".join(names)

        return self.metadata["tags"].get("name", f"<OSM {self.get_id()}>")

    def get_short_description(self) -> str:
        """Get a short, human-readable description for logging.

        Includes the brunnel type, display name, and segment count for compound brunnels.
        Format: "{Type}: {name}" or "{Type}: {name} [{count} segments]" for compound brunnels.

        Returns:
            str: A short descriptive string.
        """
        brunnel_type = self.brunnel_type.value.capitalize()
        name = self.get_display_name()
        count = ""
        if self.compound_group is not None:
            count = f" [{len(self.compound_group)} segments]"

        return f"{brunnel_type}: {name}{count}"

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
            distance = route.linestring.project(point)  # Keep in meters

            min_distance = min(min_distance, distance)
            max_distance = max(max_distance, distance)

        self.route_span = RouteSpan(min_distance, max_distance)

    def is_aligned_with_route(self, route, tolerance_degrees: float) -> bool:
        """
        Check if this brunnel's bearing is aligned with the route within tolerance.

        For each brunnel segment, projects endpoints onto the route to find the
        corresponding route substring, then checks alignment between each brunnel
        segment and each route segment in that substring. Returns True if any
        segment pair is within tolerance.

        Args:
            route: Route object representing the route
            tolerance_degrees: Allowed bearing deviation in degrees

        Returns:
            True if any brunnel segment is aligned with any route segment within tolerance
        """
        cos_max_angle = math.cos(math.radians(tolerance_degrees))
        brunnel_coords = list(self.linestring.coords)

        # Check each brunnel segment
        for b_idx in range(len(brunnel_coords) - 1):
            # Get brunnel segment endpoints
            b_start_point = Point(brunnel_coords[b_idx])
            b_end_point = Point(brunnel_coords[b_idx + 1])

            # Project brunnel endpoints onto route to get distances
            d1 = route.linestring.project(b_start_point)
            d2 = route.linestring.project(b_end_point)

            route_substring = substring(route.linestring, d1, d2)
            if route_substring.is_empty:
                continue
            route_coords = list(route_substring.coords)

            # Get brunnel segment vector
            b_vec_x = brunnel_coords[b_idx + 1][0] - brunnel_coords[b_idx][0]
            b_vec_y = brunnel_coords[b_idx + 1][1] - brunnel_coords[b_idx][1]
            b_mag = math.sqrt(b_vec_x**2 + b_vec_y**2)

            if b_mag == 0:
                continue  # Skip zero-length brunnel segment

            # Check alignment with each route segment in the substring
            for r_idx in range(len(route_coords) - 1):
                # Get route segment vector
                r_vec_x = route_coords[r_idx + 1][0] - route_coords[r_idx][0]
                r_vec_y = route_coords[r_idx + 1][1] - route_coords[r_idx][1]
                r_mag = math.sqrt(r_vec_x**2 + r_vec_y**2)

                if r_mag == 0:
                    continue  # Skip zero-length route segment

                # Calculate alignment using dot product
                # abs() handles both parallel and anti-parallel cases
                dot_product = abs(
                    (b_vec_x * r_vec_x + b_vec_y * r_vec_y) / (b_mag * r_mag)
                )

                # Ensure dot_product is not slightly > 1.0 due to precision errors
                dot_product = min(dot_product, 1.0)

                # If this segment pair is aligned within tolerance, return True
                if dot_product >= cos_max_angle:
                    return True

        # No segment pairs were aligned within tolerance
        logger.debug(f"{self.get_short_description()} is not aligned with the route")
        return False

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


def _build_node_edges(
    brunnels: Dict[str, Brunnel],
) -> Tuple[Dict[str, Set[str]], List[str]]:
    """Build edges dictionary mapping node IDs to way IDs and return eligible way IDs."""
    edges: Dict[str, Set[str]] = defaultdict(set)
    way_ids = []

    for brunnel in brunnels.values():
        # Only process brunnels that are not filtered
        if brunnel.exclusion_reason != ExclusionReason.NONE:
            continue

        way_id = brunnel.get_id()
        way_ids.append(way_id)

        # Get nodes from metadata
        nodes = brunnel.metadata.get("nodes", [])

        # Add this way ID to the edge list for each of its nodes
        for node_id in nodes:
            edges[node_id].add(way_id)

    return edges, way_ids


def _find_connected_component(
    start_way: str,
    edges: Dict[str, Set[str]],
    brunnels: Dict[str, Brunnel],
    visited_ways: Set[str],
) -> Set[str]:
    """Find all ways connected to start_way through shared nodes using BFS."""
    component: Set[str] = set()
    queue: deque[str] = deque([start_way])

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

    return component


def _find_all_connected_components(
    way_ids: List[str], edges: Dict[str, Set[str]], brunnels: Dict[str, Brunnel]
) -> List[Set[str]]:
    """Find all connected components using breadth-first search."""
    visited_ways: Set[str] = set()
    connected_components: List[Set[str]] = []

    # Process each way that hasn't been visited
    for way_id in way_ids:
        if way_id in visited_ways:
            continue

        component = _find_connected_component(way_id, edges, brunnels, visited_ways)
        connected_components.append(component)

    return connected_components


def _mark_compound_groups(
    connected_components: List[Set[str]], brunnels: Dict[str, Brunnel]
) -> None:
    """Mark compound groups for components with more than one way."""
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


def find_compound_brunnels(brunnels: Dict[str, Brunnel]) -> None:
    """
    Identify connected components of brunnels and mark compound groups.

    This function analyzes the graph formed by brunnels sharing nodes and identifies
    connected components. For components with more than one way, it constructs a compound group
    to mark them as part of the same logical structure.

    Args:
        brunnels: Dictionary of Brunnel objects to analyze
    """
    # Build edges dictionary and get eligible way IDs
    edges, way_ids = _build_node_edges(brunnels)

    # Find connected components using breadth-first search
    connected_components = _find_all_connected_components(way_ids, edges, brunnels)

    # Mark compound groups
    _mark_compound_groups(connected_components, brunnels)
