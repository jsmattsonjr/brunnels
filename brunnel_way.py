#!/usr/bin/env python3
"""
Data models for brunnel analysis.
"""

from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from enum import Enum
import logging

from geometry import Position, Geometry

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
    BICYCLE_NO = "bicycle=no"
    WATERWAY = "has waterway tag"
    RAILWAY = "railway (not abandoned)"
    POLYGON = "closed way (first node equals last node)"
    NOT_CONTAINED = "not contained within route buffer"
    NO_ROUTE_SPAN = "failed to calculate route span"
    UNALIGNED = "bearing not aligned with route"
    NOT_NEAREST = "not nearest among overlapping brunnels"
    MERGED = "merged into adjacent brunnel"

    def __str__(self) -> str:
        return self.value


class Direction(Enum):
    """Enumeration for brunnel direction relative to route."""

    FORWARD = "forward"
    REVERSE = "reverse"

    def __str__(self) -> str:
        return self.value


@dataclass
class RouteSpan:
    """Information about where a brunnel spans along a route."""

    start_distance_km: float  # Distance from route start where brunnel begins
    end_distance_km: float  # Distance from route start where brunnel ends
    length_km: float  # Length of route spanned by brunnel

    def __post_init__(self):
        """Calculate length after initialization."""
        self.length_km = self.end_distance_km - self.start_distance_km


@dataclass
class BrunnelWay(Geometry):
    coords: List[Position]
    metadata: Dict[str, Any]
    brunnel_type: BrunnelType
    contained_in_route: bool = False
    filter_reason: FilterReason = FilterReason.NONE
    route_span: Optional[RouteSpan] = None

    @property
    def coordinate_list(self) -> List[Position]:
        """Return the list of Position objects for this geometry."""
        return self.coords

    @classmethod
    def determine_type(cls, metadata: Dict[str, Any]) -> BrunnelType:
        """
        Determine brunnel type from OSM metadata.

        Args:
            metadata: OSM metadata for the brunnel

        Returns:
            BrunnelType enum value
        """
        tags = metadata.get("tags", {})

        # Check for tunnel first (tunnels are often more specific)
        if "tunnel" in tags and tags["tunnel"] not in ["no", "false"]:
            return BrunnelType.TUNNEL

        # Otherwise, assume it's a bridge
        return BrunnelType.BRIDGE

    @classmethod
    def should_filter(
        cls, metadata: Dict[str, Any], keep_polygons: bool = False
    ) -> FilterReason:
        """
        Determine if a brunnel should be filtered out based on cycling relevance and geometry.

        Args:
            metadata: OSM metadata for the brunnel
            keep_polygons: If False, filter out closed ways (first node == last node)

        Returns:
            FilterReason.NONE if the brunnel should be kept, otherwise returns
            the reason for filtering.
        """
        # Check for polygon (closed way) if keep_polygons is False
        if not keep_polygons:
            nodes = metadata.get("nodes", [])
            if len(nodes) >= 2 and nodes[0] == nodes[-1]:
                return FilterReason.POLYGON

        tags = metadata.get("tags", {})

        # Check bicycle tag first - highest priority
        if "bicycle" in tags:
            if tags["bicycle"] == "no":
                return FilterReason.BICYCLE_NO
            else:
                # bicycle=* (anything other than "no") - keep and skip other checks
                return FilterReason.NONE

        # Check for cycleway - keep and skip other checks
        if tags.get("highway") == "cycleway":
            return FilterReason.NONE

        # Check for waterway - filter out
        if "waterway" in tags:
            return FilterReason.WATERWAY

        # Check for railway - filter out unless abandoned
        if "railway" in tags:
            if tags["railway"] != "abandoned":
                return FilterReason.RAILWAY

        # Default: keep the brunnel
        return FilterReason.NONE

    @classmethod
    def from_overpass_data(
        cls, way_data: Dict[str, Any], keep_polygons: bool = False
    ) -> "BrunnelWay":
        """
        Parse a single way from Overpass response into BrunnelWay object.

        Args:
            way_data: Raw way data from Overpass API
            keep_polygons: Whether to keep closed ways (polygons)

        Returns:
            BrunnelWay object
        """
        # Extract coordinates from geometry
        coords = []
        if "geometry" in way_data:
            for node in way_data["geometry"]:
                coords.append(Position(latitude=node["lat"], longitude=node["lon"]))

        brunnel_type = cls.determine_type(way_data)
        filter_reason = cls.should_filter(way_data, keep_polygons)

        return cls(
            coords=coords,
            metadata=way_data,
            brunnel_type=brunnel_type,
            filter_reason=filter_reason,
        )

    def calculate_route_span(
        self, route, cumulative_distances: List[float]
    ) -> RouteSpan:
        """
        Calculate the span of this brunnel along the route.

        Args:
            route: Route object representing the route
            cumulative_distances: Pre-calculated cumulative distances along route

        Returns:
            RouteSpan object with start/end distances and length
        """
        if not self.coords:
            return RouteSpan(0.0, 0.0, 0.0)

        # Import here to avoid circular imports
        from distance_utils import find_closest_point_on_route

        min_distance = float("inf")
        max_distance = -float("inf")

        # Find the closest route point for each brunnel coordinate
        for brunnel_point in self.coords:
            cumulative_dist, _ = find_closest_point_on_route(
                brunnel_point, route.positions, cumulative_distances
            )

            min_distance = min(min_distance, cumulative_dist)
            max_distance = max(max_distance, cumulative_dist)

        return RouteSpan(min_distance, max_distance, max_distance - min_distance)

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
                f"Failed to check containment for brunnel {self.metadata.get('id', 'unknown')}: {e}"
            )
            return False

    def is_aligned_with_route(self, route, tolerance_degrees: float) -> bool:
        """
        Check if this brunnel's bearing is aligned with the route at their closest point.

        Args:
            route: Route object representing the route
            tolerance_degrees: Allowed bearing deviation in degrees

        Returns:
            True if brunnel is aligned with route within tolerance, False otherwise
        """
        if not self.coords or len(self.coords) < 2:
            logger.debug(
                f"Brunnel {self.metadata.get('id', 'unknown')} has insufficient coordinates for bearing calculation"
            )
            return False

        if not route.positions or len(route.positions) < 2:
            logger.debug("Route has insufficient coordinates for bearing calculation")
            return False

        # Import here to avoid circular imports
        from distance_utils import (
            find_closest_segments,
            calculate_bearing,
            bearings_aligned,
        )

        # Find closest segments between brunnel and route
        brunnel_segment, route_segment = find_closest_segments(
            self.coords, route.positions
        )

        if brunnel_segment is None or route_segment is None:
            logger.debug(
                f"Could not find closest segments for brunnel {self.metadata.get('id', 'unknown')}"
            )
            return False

        # Extract segment coordinates
        _, brunnel_start, brunnel_end = brunnel_segment
        _, route_start, route_end = route_segment

        # Calculate bearings for both segments
        brunnel_bearing = calculate_bearing(brunnel_start, brunnel_end)
        route_bearing = calculate_bearing(route_start, route_end)

        # Check if bearings are aligned
        aligned = bearings_aligned(brunnel_bearing, route_bearing, tolerance_degrees)

        logger.debug(
            f"Brunnel {self.metadata.get('id', 'unknown')}: "
            f"brunnel_bearing={brunnel_bearing:.1f}°, route_bearing={route_bearing:.1f}°, "
            f"aligned={aligned} (tolerance={tolerance_degrees}°)"
        )

        return aligned

    def shares_node_with(self, other: "BrunnelWay") -> bool:
        """
        Check if this brunnel shares a node with another brunnel.

        Args:
            other: Another BrunnelWay object

        Returns:
            True if they share a node, False otherwise
        """
        nodes1 = self.metadata.get("nodes", [])
        nodes2 = other.metadata.get("nodes", [])

        if not nodes1 or not nodes2:
            return False

        # Check if any node from this brunnel appears in the other brunnel
        nodes1_set = set(nodes1)
        nodes2_set = set(nodes2)

        return bool(nodes1_set & nodes2_set)

    def to_html(self) -> str:
        """
        Format this brunnel's metadata into HTML for popup display.

        Returns:
            HTML-formatted string with metadata
        """
        html_parts = []
        tags = self.metadata.get("tags", {})

        # Add name most prominently if present
        if "name" in tags:
            html_parts.append(f"<b>{tags['name']}</b>")

        # Add alt_name next if present
        if "alt_name" in tags:
            html_parts.append(f"<br><b>AKA:</b> {tags['alt_name']}")

        # Add OSM ID
        osm_id = self.metadata.get("id", "unknown")
        html_parts.append(f"<br><b>OSM ID:</b> {osm_id}")

        # Add remaining OSM tags (excluding name and alt_name which we already showed)
        remaining_tags = {
            k: v for k, v in tags.items() if k not in ["name", "alt_name"]
        }
        if remaining_tags:
            html_parts.append("<br><b>Tags:</b>")
            for key, value in sorted(remaining_tags.items()):
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
