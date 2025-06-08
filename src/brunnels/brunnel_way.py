#!/usr/bin/env python3
"""
BrunnelWay implementation for individual bridge/tunnel segments.
"""

from typing import Optional, List, Dict, Any
from dataclasses import dataclass
import logging

from .geometry import Position
from .brunnel import Brunnel, BrunnelType, FilterReason, RouteSpan

logger = logging.getLogger(__name__)


@dataclass
class BrunnelWay(Brunnel):
    """A single bridge or tunnel way from OpenStreetMap."""

    coords: List[Position]
    metadata: Dict[str, Any]

    def __init__(
        self,
        coords: List[Position],
        metadata: Dict[str, Any],
        brunnel_type: BrunnelType,
        contained_in_route: bool = False,
        filter_reason: FilterReason = FilterReason.NONE,
        route_span: Optional[RouteSpan] = None,
    ):
        super().__init__(brunnel_type, contained_in_route, filter_reason, route_span)
        self.coords = coords
        self.metadata = metadata

    @property
    def coordinate_list(self) -> List[Position]:
        """Return the list of Position objects for this geometry."""
        return self.coords

    def get_id(self) -> str:
        """Get a string identifier for this brunnel."""
        return str(self.metadata.get("id", "unknown"))

    def get_display_name(self) -> str:
        """Get the display name for this brunnel."""
        return self.metadata.get("tags", {}).get("name", "unnamed")

    def get_short_description(self) -> str:
        """Get a short description for logging."""
        brunnel_type = self.brunnel_type.value.capitalize()
        name = self.get_display_name()
        return f"{brunnel_type}: {name} ({self.get_id()})"

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
        html_parts.append(f"<br><b>OSM ID:</b> {self.get_id()}")

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
