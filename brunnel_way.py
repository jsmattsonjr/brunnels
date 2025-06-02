#!/usr/bin/env python3
"""
Data models for brunnel analysis.
"""

from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from enum import Enum
from geometry import Position, Geometry


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
