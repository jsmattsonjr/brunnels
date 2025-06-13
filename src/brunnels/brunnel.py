#!/usr/bin/env python3
""" """

from dataclasses import dataclass
from typing import Optional, List, Dict, Any, Set
from collections import defaultdict, deque
from dataclasses import dataclass
from enum import Enum
import logging

from .geometry import Position, Geometry
from .geometry_utils import (
    find_closest_segments,
    bearings_aligned,
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


@dataclass
class RouteSpan:
    """Information about where a brunnel spans along a route."""

    start_distance: float  # Distance from route start where brunnel begins
    end_distance: float  # Distance from route start where brunnel ends


@dataclass
class Brunnel(Geometry):
    """A single bridge or tunnel way from OpenStreetMap."""

    coords: List[Position]
    metadata: Dict[str, Any]

    def __init__(
        self,
        coords: List[Position],
        metadata: Dict[str, Any],
        brunnel_type: BrunnelType,
        filter_reason: FilterReason = FilterReason.NONE,
        route_span: Optional[RouteSpan] = None,
    ):
        super().__init__()
        self.coords = coords
        self.metadata = metadata
        self.brunnel_type = brunnel_type
        self.filter_reason = filter_reason
        self.route_span = route_span

    @property
    def coordinate_list(self) -> List[Position]:
        """Return the list of Position objects for this geometry."""
        return self.coords

    def is_compound_brunnel(self) -> bool:
        """
        Check if this brunnel is part of a compound group.
        """
        return "compound_group" in self.metadata

    def is_representative(self) -> bool:
        if not self.is_compound_brunnel():
            return True
        compound_group = self.metadata.get("compound_group", [])
        return compound_group.index(self) == 0

    def get_id(self) -> str:
        """Get a string identifier for this brunnel."""
        if self.is_compound_brunnel():
            return ";".join(
                str(component.metadata.get("id", "unknown"))
                for component in self.metadata.get("compound_group", [])
            )
        return str(self.metadata.get("id", "unknown"))

    def get_display_name(self) -> str:
        """Get the display name for this brunnel."""
        return self.metadata.get("tags", {}).get("name", "unnamed")

    def get_short_description(self) -> str:
        """Get a short description for logging."""
        brunnel_type = self.brunnel_type.value.capitalize()
        name = self.get_display_name()
        if self.is_compound_brunnel():
            component_count = len(self.metadata.get("compound_group", []))
            return f"Compound {brunnel_type}: {name} ({self.get_id()}) [{component_count} segments]"
        return f"{brunnel_type}: {name} ({self.get_id()})"

    def get_log_description(self) -> str:
        """Get a standardized description for logging with route span info."""
        route_span = self.get_route_span()
        if route_span is not None:
            span_info = f"{route_span.start_distance:.2f}-{route_span.end_distance:.2f} km (length: {route_span.end_distance - route_span.start_distance:.2f} km)"
            return f"{self.get_short_description()} {span_info}"
        else:
            return f"{self.get_short_description()} (no route span)"

    def get_route_span(self) -> Optional[RouteSpan]:
        if self.is_compound_brunnel():
            compound_group = self.metadata.get("compound_group", [])
            return RouteSpan(
                compound_group[0].route_span.start_distance,
                compound_group[-1].route_span.end_distance,
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

    def to_html(self) -> str:
        """
        Format this brunnel's metadata into HTML for popup display.

        Returns:
            HTML-formatted string with metadata
        """
        html_parts = []

        if self.is_compound_brunnel():
            compound_group = self.metadata.get("compound_group", [])
            html_parts.append(
                f"Segment {compound_group.index(self)+1} of {len(compound_group)} in compound group<br>"
            )
        tags = self.metadata.get("tags", {})

        # Add name most prominently if present
        if "name" in tags:
            html_parts.append(f"<b>{tags['name']}</b>")

        # Add alt_name next if present
        if "alt_name" in tags:
            html_parts.append(f"<br><b>AKA:</b> {tags['alt_name']}")

        # Add OSM ID
        html_parts.append(f"<br><b>OSM ID:</b> {self.get_id()}")

        # Add remaining OSM tags (excluding name and alt_name which we already showed)
        remaining_tags = {
            k: v for k, v in tags.items() if k not in ["name", "alt_name"]
        }
        if remaining_tags:
            html_parts.append("<br><b>Tags:</b>")
            for key, value in sorted(remaining_tags.items()):
                if (
                    key == "bicycle"
                    and value == "no"
                    or key == "waterway"
                    or key == "railway"
                    and value != "abandoned"
                ):
                    value = f"<span style='color: red;'>{value}</span>"
                html_parts.append(f"<br>&nbsp;&nbsp;<i>{key}:</i> {value}")

        # Add other metadata (excluding tags and id which we already handled,
        # geometry which is very long, and type which is always "way")
        other_data = {
            k: v
            for k, v in self.metadata.items()
            if k not in ["tags", "id", "geometry", "type"]
        }
        if other_data:
            html_parts.append("<br><b>Other:</b>")
            for key, value in sorted(other_data.items()):
                # Handle nested dictionaries or lists
                if isinstance(value, (dict, list)):
                    # Use structured formatting for nodes and bounds
                    if key in ["nodes", "bounds"]:
                        formatted_value = self._format_complex_value(key, value, 0)
                        # Add proper indentation for the "Other:" section
                        indented_lines = []
                        for line in formatted_value.split("<br>"):
                            if line.strip():  # Skip empty lines
                                indented_lines.append(f"&nbsp;&nbsp;{line}")
                        html_parts.append("<br>" + "<br>".join(indented_lines))
                    else:
                        # Keep truncation for other long nested data
                        value_str = str(value)
                        if len(value_str) > 50:
                            value_str = value_str[:47] + "..."
                        html_parts.append(f"<br>&nbsp;&nbsp;<i>{key}:</i> {value_str}")
                else:
                    value_str = str(value)
                    html_parts.append(f"<br>&nbsp;&nbsp;<i>{key}:</i> {value_str}")

        return "".join(html_parts)

    def _format_complex_value(self, key: str, value: Any, indent_level: int = 0) -> str:
        """
        Format complex values (dicts, lists) into readable HTML with proper indentation.

        Args:
            key: The key name
            value: The value to format
            indent_level: Current indentation level

        Returns:
            Formatted HTML string
        """
        indent = "&nbsp;" * (indent_level * 4)

        if isinstance(value, dict):
            if not value:
                return f"{indent}<i>{key}:</i> {{}}"

            parts = [f"{indent}<i>{key}:</i>"]
            for k, v in value.items():
                if isinstance(v, (dict, list)):
                    parts.append(self._format_complex_value(k, v, indent_level + 1))
                else:
                    nested_indent = "&nbsp;" * ((indent_level + 1) * 4)
                    parts.append(f"{nested_indent}<i>{k}:</i> {v}")
            return "<br>".join(parts)

        elif isinstance(value, list):
            if not value:
                return f"{indent}<i>{key}:</i> []"

            parts = [f"{indent}<i>{key}:</i>"]
            for i, item in enumerate(value):
                if isinstance(item, (dict, list)):
                    parts.append(
                        self._format_complex_value(f"[{i}]", item, indent_level + 1)
                    )
                else:
                    nested_indent = "&nbsp;" * ((indent_level + 1) * 4)
                    parts.append(f"{nested_indent}[{i}]: {item}")
            return "<br>".join(parts)

        else:
            return f"{indent}<i>{key}:</i> {value}"

    def is_contained_by(self, route_geometry) -> bool:
        """
        Check if this brunnel is completely contained within a route geometry.

        Args:
            route_geometry: Shapely geometry object representing the buffered route polygon

        Returns:
            True if the route geometry completely contains this brunnel, False otherwise
        """
        try:
            # Get cached LineString from brunnel
            brunnel_line = self.get_linestring()
            if brunnel_line is None:
                return False

            # Check if route geometry completely contains the brunnel
            return route_geometry.contains(brunnel_line)

        except Exception as e:
            logger.warning(
                f"Failed to check containment for brunnel {self.get_id()}: {e}"
            )
            return False

    def calculate_route_span(self, route) -> None:
        """
        Calculate the span of this brunnel along the route.

        Args:
            route: Route object representing the route
        """
        coords = self.coordinate_list
        if not coords:
            raise ValueError(
                f"{self.get_short_description()} has no coordinates to calculate route span"
            )
        if len(coords) < 2:
            raise ValueError(
                f"{self.get_short_description()} has insufficient coordinates to calculate route span"
            )

        min_distance = float("inf")
        max_distance = -float("inf")

        # Find the closest route point for each brunnel coordinate
        for brunnel_point in coords:
            distance, _ = route.closest_point_to(brunnel_point)

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

        coords = self.coordinate_list
        if not coords or len(coords) < 2:
            logger.debug(
                f"{self.get_short_description()} has insufficient coordinates for bearing calculation"
            )
            return False

        if len(route) < 2:  # Check length using Route's __len__
            logger.debug("Route has insufficient coordinates for bearing calculation")
            return False

        # Find closest segments between brunnel and route
        # route.coordinate_list returns List[Position]
        brunnel_segment, route_segment = find_closest_segments(
            coords, route.coordinate_list
        )

        if brunnel_segment is None or route_segment is None:
            logger.debug(
                f"Could not find closest segments for {self.get_short_description()}"
            )
            return False

        # Extract segment coordinates
        _, brunnel_start, brunnel_end = brunnel_segment
        _, route_start, route_end = route_segment

        # Calculate bearings for both segments
        brunnel_bearing = brunnel_start.bearing_to(brunnel_end)
        route_bearing = route_start.bearing_to(route_end)

        # Check if bearings are aligned
        aligned = bearings_aligned(brunnel_bearing, route_bearing, tolerance_degrees)

        logger.debug(
            f"{self.get_short_description()}: brunnel_bearing={brunnel_bearing:.1f}°, route_bearing={route_bearing:.1f}°, aligned={aligned} (tolerance={tolerance_degrees}°)"
        )

        return aligned

    @classmethod
    def from_overpass_data(cls, way_data: Dict[str, Any]) -> "Brunnel":
        """
        Parse a single way from Overpass response into Brunnel object.

        Args:
            way_data: Raw way data from Overpass API

        Returns:
            Brunnel object
        """
        # Extract coordinates from geometry
        coords = []
        if "geometry" in way_data:
            for node in way_data["geometry"]:
                coords.append(Position(latitude=node["lat"], longitude=node["lon"]))

        tags = way_data.get("tags", {})
        brunnel_type = BrunnelType.BRIDGE  # Default to bridge
        if tags.get("tunnel", "no") not in ["no", "false"]:
            brunnel_type = BrunnelType.TUNNEL

        return cls(
            coords=coords,
            metadata=way_data,
            brunnel_type=brunnel_type,
        )


def find_compound_brunnels(brunnels: Dict[str, Brunnel]) -> None:
    """
    Identify connected components of brunnels and mark compound groups.

    This function analyzes the graph formed by brunnels sharing nodes and identifies
    connected components. For components with more than one way, it adds compound_group
    metadata to mark them as part of the same logical structure.

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
            # Add compound_group metadata to all brunnels in this component
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
                brunnel.metadata["compound_group"] = compound_group
