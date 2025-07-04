#!/usr/bin/env python3
"""
Route visualization using folium maps.
"""

from typing import Dict, Any
import logging
import argparse
import folium
from folium.template import Template

from .brunnel import Brunnel, BrunnelType, ExclusionReason
from .route import Route
from .metrics import BrunnelMetrics
from .overpass import ACTIVE_RAILWAY_TYPES

logger = logging.getLogger(__name__)


class BrunnelLegend(folium.MacroElement):
    """Custom legend for brunnel visualization with dynamic counts."""

    def __init__(self, metrics: BrunnelMetrics):
        super().__init__()
        self.bridge_count = metrics.bridge_counts.get("total", 0)
        self.tunnel_count = metrics.tunnel_counts.get("total", 0)
        self.contained_bridge_count = metrics.bridge_counts.get("contained", 0)
        self.contained_tunnel_count = metrics.tunnel_counts.get("contained", 0)
        self.alternative_bridge_count = metrics.bridge_counts.get("alternative", 0)
        self.alternative_tunnel_count = metrics.tunnel_counts.get("alternative", 0)
        self.misaligned_bridge_count = metrics.bridge_counts.get("misaligned", 0)
        self.misaligned_tunnel_count = metrics.tunnel_counts.get("misaligned", 0)

        # Use folium's template string approach
        self._template = Template(
            """
        {% macro html(this, kwargs) %}
        <div id="brunnel-legend" style="
            position: fixed;
            bottom: 50px;
            left: 50px;
            width: 230px;
            min-height: 90px;
            max-height: 200px;
            background-color: white;
            border: 2px solid grey;
            z-index: 9999;
            font-size: 13px;
            padding: 12px;
            font-family: Arial, sans-serif;
            border-radius: 5px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.2);
            overflow: hidden;
            box-sizing: border-box;
        ">
            <b>Legend</b><br>
            <div style="margin: 4px 0; line-height: 1.3;">
                <span style="color: #2E86AB; font-weight: normal; font-size: 18px;">—</span>
                GPX Route
            </div>
            <div style="margin: 4px 0; line-height: 1.3;">
                <span style="color: #D23C4C; font-weight: bold; font-size: 18px;">—</span>
                Bridges ({{ this.contained_bridge_count }})
            </div>
            <div style="margin: 4px 0; line-height: 1.3;">
                <span style="color: #69498F; font-weight: bold; font-size: 18px;">—</span>
                Tunnels ({{ this.contained_tunnel_count }})
            </div>
            {% if this.alternative_bridge_count > 0 %}
            <div style="margin: 4px 0; line-height: 1.3;">
                <span style="color: #FF6B35; font-weight: bold; font-size: 18px;">—</span>
                Alternative Bridges ({{ this.alternative_bridge_count }})
            </div>
            {% endif %}
            {% if this.alternative_tunnel_count > 0 %}
            <div style="margin: 4px 0; line-height: 1.3;">
                <span style="color: #9D4EDD; font-weight: bold; font-size: 18px;">—</span>
                Alternative Tunnels ({{ this.alternative_tunnel_count }})
            </div>
            {% endif %}
            {% if this.misaligned_bridge_count > 0 %}
            <div style="margin: 4px 0; line-height: 1.3;">
                <span style="color: #FF8C00; font-weight: bold; font-size: 18px;">—</span>
                Misaligned Bridges ({{ this.misaligned_bridge_count }})
            </div>
            {% endif %}
            {% if this.misaligned_tunnel_count > 0 %}
            <div style="margin: 4px 0; line-height: 1.3;">
                <span style="color: #DAA520; font-weight: bold; font-size: 18px;">—</span>
                Misaligned Tunnels ({{ this.misaligned_tunnel_count }})
            </div>
            {% endif %}
        </div>
        {% endmacro %}
        """
        )


def format_complex_value(key: str, value: Any, indent_level: int = 0) -> str:
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
                parts.append(format_complex_value(k, v, indent_level + 1))
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
                parts.append(format_complex_value(f"[{i}]", item, indent_level + 1))
            else:
                nested_indent = "&nbsp;" * ((indent_level + 1) * 4)
                parts.append(f"{nested_indent}[{i}]: {item}")
        return "<br>".join(parts)

    else:
        return f"{indent}<i>{key}:</i> {value}"


def _format_brunnel_names(tags: Dict[str, str]) -> str:
    """
    Format brunnel name and alt_name into HTML.

    Args:
        tags: OSM tags dictionary

    Returns:
        HTML string with formatted names
    """
    html_parts = []

    # Add name most prominently if present
    if "name" in tags:
        html_parts.append(f"<b>{tags['name']}</b>")

    # Add alt_name next if present
    if "alt_name" in tags:
        html_parts.append(f"<br><b>AKA:</b> {tags['alt_name']}")

    return "".join(html_parts)


def _format_osm_tags(tags: Dict[str, str]) -> str:
    """
    Format OSM tags (excluding name and alt_name) into HTML.

    Args:
        tags: OSM tags dictionary

    Returns:
        HTML string with formatted tags
    """
    # Add remaining OSM tags (excluding name and alt_name which we already showed)
    remaining_tags = {k: v for k, v in tags.items() if k not in ["name", "alt_name"]}
    if not remaining_tags:
        return ""

    html_parts = ["<br><b>Tags:</b>"]
    for key, value in sorted(remaining_tags.items()):
        highlight = (
            key == "bicycle"
            and value == "no"
            or key == "waterway"
            or key == "railway"
            and value in ACTIVE_RAILWAY_TYPES
        )
        prefix = "<span style='color: red;'>" if highlight else ""
        suffix = "</span>" if highlight else ""
        html_parts.append(f"<br>&nbsp;&nbsp;{prefix}<i>{key}:</i> {value}{suffix}")

    return "".join(html_parts)


def _format_other_metadata(metadata: Dict[str, Any]) -> str:
    """
    Format other metadata (non-tag, non-ID fields) into HTML.

    Args:
        metadata: Brunnel metadata dictionary

    Returns:
        HTML string with formatted metadata
    """
    # Add other metadata (excluding tags and id which we already handled,
    # geometry which is very long, and type which is always "way")
    other_data = {
        k: v for k, v in metadata.items() if k not in ["tags", "id", "geometry", "type"]
    }
    if not other_data:
        return ""

    html_parts = ["<br><b>Other:</b>"]
    for key, value in sorted(other_data.items()):
        # Handle nested dictionaries or lists
        if isinstance(value, (dict, list)):
            # Use structured formatting for nodes and bounds
            if key in ["nodes", "bounds"]:
                formatted_value = format_complex_value(key, value, 0)
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


def brunnel_to_html(brunnel: Brunnel) -> str:
    """
    Format a brunnel's metadata into HTML for popup display.

    Args:
        brunnel: The Brunnel object to format

    Returns:
        HTML-formatted string with metadata
    """
    html_parts = []

    if brunnel.compound_group is not None:
        compound_group = brunnel.compound_group
        html_parts.append(
            f"Segment {compound_group.index(brunnel)+1} of {len(compound_group)} in compound group<br>"
        )

    tags = brunnel.metadata.get("tags", {})

    # Add formatted names
    names_html = _format_brunnel_names(tags)
    if names_html:
        html_parts.append(names_html)

    # Add OSM ID
    html_parts.append(f"<br><b>OSM ID:</b> {brunnel.get_id()}")

    # Add formatted OSM tags
    tags_html = _format_osm_tags(tags)
    if tags_html:
        html_parts.append(tags_html)

    # Add formatted other metadata
    other_html = _format_other_metadata(brunnel.metadata)
    if other_html:
        html_parts.append(other_html)

    return "".join(html_parts)


def _setup_map_with_layers(center_lat: float, center_lon: float) -> folium.Map:
    """
    Create and configure a folium map with tile layers.

    Args:
        center_lat: Center latitude for the map
        center_lon: Center longitude for the map

    Returns:
        Configured folium Map instance
    """
    route_map = folium.Map(
        location=[center_lat, center_lon],
        tiles=None,
    )

    # Add Standard layer (CartoDB positron)
    folium.TileLayer(
        tiles="CartoDB positron",
        attr=(
            "&copy; <a href='https://www.openstreetmap.org/copyright'>OpenStreetMap</a> "
            "contributors &copy; <a href='https://carto.com/attributions'>CARTO</a>"
        ),
        name="Standard",
        control=True,
        show=True,  # Show by default
    ).add_to(route_map)

    # Add Satellite layer (Esri World Imagery)
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr=(
            "Tiles &copy; Esri &mdash; Source: Esri, i-cubed, USDA, USGS, AEX, GeoEye, "
            "Getmapping, Aerogrid, IGN, IGP, UPR-EGP, and the GIS User Community"
        ),
        name="Satellite",
        control=True,
        show=False,  # Initially hidden
    ).add_to(route_map)

    # Add LayerControl
    folium.LayerControl().add_to(route_map)

    return route_map


def _add_route_to_map(route_map: folium.Map, route: Route) -> None:
    """
    Add route polyline and start/end markers to the map.

    Args:
        route_map: Folium map instance
        route: Route object to display
    """
    # Convert route to coordinate pairs for folium
    coordinates = [[pos.latitude, pos.longitude] for pos in route.coords]

    # Add route as polyline
    folium.PolyLine(
        coordinates,
        color="#2E86AB",
        weight=2,
        opacity=0.6,
        popup="GPX Route",
        z_index=1,
    ).add_to(route_map)

    # Add start and end markers
    folium.Marker(
        [route[0].latitude, route[0].longitude],
        popup="Start",
        icon=folium.Icon(color="green", icon="play"),
    ).add_to(route_map)

    folium.Marker(
        [route[-1].latitude, route[-1].longitude],
        popup="End",
        icon=folium.Icon(color="red", icon="stop"),
    ).add_to(route_map)


def _get_brunnel_style(brunnel: Brunnel) -> Dict[str, Any]:
    """
    Determine color, weight, and opacity for a brunnel based on its type and exclusion reason.

    Args:
        brunnel: Brunnel object to style

    Returns:
        Dictionary with style properties (color, weight, opacity)
    """
    exclusion_reason = brunnel.exclusion_reason
    brunnel_type = brunnel.brunnel_type

    # Set color and style based on inclusion status
    if exclusion_reason == ExclusionReason.NONE:
        # Included brunnels with 80% saturation
        opacity = 0.9
        weight = 4
        if brunnel_type == BrunnelType.BRIDGE:
            color = "#D23C4C"  # Included Bridges (80% saturation)
        else:  # TUNNEL
            color = "#69498F"  # Included Tunnels (80% saturation)
    elif exclusion_reason == ExclusionReason.ALTERNATIVE:
        # Alternative brunnels with yellow tinge (fully saturated)
        opacity = 0.9
        weight = 3
        if brunnel_type == BrunnelType.BRIDGE:
            color = "#FF6B35"  # Alternative Bridges (red-orange, yellow tinge)
        else:  # TUNNEL
            color = "#9D4EDD"  # Alternative Tunnels (purple with yellow tinge)
    else:  # MISALIGNED
        # Misaligned brunnels with more yellow tinge than alternatives
        opacity = 0.9
        weight = 3
        if brunnel_type == BrunnelType.BRIDGE:
            color = "#FF8C00"  # Misaligned Bridges (dark orange, more yellow)
        else:  # TUNNEL
            color = "#DAA520"  # Misaligned Tunnels (goldenrod, more yellow)

    return {"color": color, "weight": weight, "opacity": opacity}


def _add_brunnels_to_map(route_map: folium.Map, brunnels: Dict[str, Brunnel]) -> None:
    """
    Add brunnels to the map with appropriate styling and popups.

    Args:
        route_map: Folium map instance
        brunnels: Dictionary of Brunnel objects to display
    """
    for brunnel in brunnels.values():
        brunnel_coords = [[pos.latitude, pos.longitude] for pos in brunnel.coords]
        if not brunnel_coords:
            continue

        exclusion_reason = brunnel.exclusion_reason
        route_span = brunnel.get_route_span()

        # Display included brunnels, "alternative", and "misaligned" excluded brunnels
        if exclusion_reason not in [
            ExclusionReason.NONE,
            ExclusionReason.ALTERNATIVE,
            ExclusionReason.MISALIGNED,
        ]:
            continue

        # Get styling for this brunnel
        style = _get_brunnel_style(brunnel)

        # Create popup text with full metadata
        if exclusion_reason == ExclusionReason.NONE:
            if route_span:
                status = (
                    f"{route_span.start_distance/1000:.2f} - {route_span.end_distance/1000:.2f} km; "
                    f"length: {(route_span.end_distance - route_span.start_distance)/1000:.2f} km"
                )
            else:
                status = "included"
        elif exclusion_reason == ExclusionReason.ALTERNATIVE:
            status = "alternative overlapping brunnel"
        else:  # MISALIGNED
            status = "not aligned with route"

        popup_header = (
            f"<b>{brunnel.brunnel_type.value.capitalize()}</b> ({status})<br>"
        )
        metadata_html = brunnel_to_html(brunnel)
        popup_text = popup_header + metadata_html

        # Add brunnel to map
        folium.PolyLine(
            brunnel_coords,
            color=style["color"],
            weight=style["weight"],
            opacity=style["opacity"],
            popup=folium.Popup(popup_text, max_width=400),
            z_index=2,  # Ensure brunnels are above route
        ).add_to(route_map)


def create_route_map(
    route: Route,
    output_filename: str,
    brunnels: Dict[str, Brunnel],
    metrics: BrunnelMetrics,
    args: argparse.Namespace,
) -> None:
    """
    Create an interactive map showing the route and nearby bridges/tunnels, save as HTML.

    Args:
        route: Route object representing the route
        output_filename: Path where HTML map file should be saved
        brunnels: Dictionary of Brunnel objects to display on map
        metrics: BrunnelMetrics containing pre-collected metrics
        args: argparse.Namespace object containing settings like buffer

    Raises:
        ValueError: If route is empty
    """
    if not route:
        raise ValueError("Cannot create map for empty route")

    # Calculate buffered bounding box using existing function
    south, west, north, east = route.get_bbox(args.query_buffer)

    center_lat = (south + north) / 2
    center_lon = (west + east) / 2

    logger.debug(f"Creating map centered at ({center_lat:.4f}, {center_lon:.4f})")

    # Create and configure map with layers
    route_map = _setup_map_with_layers(center_lat, center_lon)

    # Add route to map
    _add_route_to_map(route_map, route)

    # Add brunnels to map
    _add_brunnels_to_map(route_map, brunnels)

    # Add legend with dynamic counts from metrics
    legend = BrunnelLegend(metrics)
    route_map.add_child(legend)

    # Fit map bounds to buffered route area
    bounds = [[south, west], [north, east]]  # Southwest corner  # Northeast corner
    route_map.fit_bounds(bounds)

    route_map.save(output_filename)

    logger.debug(
        f"Map saved to {output_filename} with {metrics.bridge_counts.get('contained', 0)}/{metrics.bridge_counts.get('total', 0)} bridges and {metrics.tunnel_counts.get('contained', 0)}/{metrics.tunnel_counts.get('total', 0)} tunnels nearby route"
    )
