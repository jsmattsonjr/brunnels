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

logger = logging.getLogger(__name__)


class BrunnelLegend(folium.MacroElement):
    """Custom legend for brunnel visualization with dynamic counts."""

    def __init__(self, metrics: BrunnelMetrics):
        super().__init__()
        self.bridge_count = metrics.bridge_counts.get("total", 0)
        self.tunnel_count = metrics.tunnel_counts.get("total", 0)
        self.contained_bridge_count = metrics.bridge_counts.get("contained", 0)
        self.contained_tunnel_count = metrics.tunnel_counts.get("contained", 0)
        self.not_nearest_bridge_count = metrics.bridge_counts.get(
            "not_nearest_among_overlapping_brunnels", 0
        )
        self.not_nearest_tunnel_count = metrics.tunnel_counts.get(
            "not_nearest_among_overlapping_brunnels", 0
        )

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
            max-height: 150px;
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
                Included Bridges ({{ this.contained_bridge_count }})
            </div>
            <div style="margin: 4px 0; line-height: 1.3;">
                <span style="color: #69498F; font-weight: bold; font-size: 18px;">—</span>
                Included Tunnels ({{ this.contained_tunnel_count }})
            </div>
            {% if this.not_nearest_bridge_count > 0 %}
            <div style="margin: 4px 0; line-height: 1.3;">
                <span style="color: #DF94A7; font-weight: bold; font-size: 18px;">—</span>
                Not Nearest Bridges ({{ this.not_nearest_bridge_count }})
            </div>
            {% endif %}
            {% if this.not_nearest_tunnel_count > 0 %}
            <div style="margin: 4px 0; line-height: 1.3;">
                <span style="color: #B495C2; font-weight: bold; font-size: 18px;">—</span>
                Not Nearest Tunnels ({{ this.not_nearest_tunnel_count }})
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

    # Add name most prominently if present
    if "name" in tags:
        html_parts.append(f"<b>{tags['name']}</b>")

    # Add alt_name next if present
    if "alt_name" in tags:
        html_parts.append(f"<br><b>AKA:</b> {tags['alt_name']}")

    # Add OSM ID
    html_parts.append(f"<br><b>OSM ID:</b> {brunnel.get_id()}")

    # Add remaining OSM tags (excluding name and alt_name which we already showed)
    remaining_tags = {k: v for k, v in tags.items() if k not in ["name", "alt_name"]}
    if remaining_tags:
        html_parts.append("<br><b>Tags:</b>")
        for key, value in sorted(remaining_tags.items()):
            highlight = (
                key == "bicycle"
                and value == "no"
                or key == "waterway"
                or key == "railway"
                and value != "abandoned"
            )
            prefix = "<span style='color: red;'>" if highlight else ""
            suffix = "</span>" if highlight else ""
            html_parts.append(f"<br>&nbsp;&nbsp;{prefix}<i>{key}:</i> {value}{suffix}")

    # Add other metadata (excluding tags and id which we already handled,
    # geometry which is very long, and type which is always "way")
    other_data = {
        k: v
        for k, v in brunnel.metadata.items()
        if k not in ["tags", "id", "geometry", "type"]
    }
    if other_data:
        html_parts.append("<br><b>Other:</b>")
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
    south, west, north, east = route.get_bbox(args.bbox_buffer)

    center_lat = (south + north) / 2
    center_lon = (west + east) / 2

    logger.debug(f"Creating map centered at ({center_lat:.4f}, {center_lon:.4f})")

    # Initialize map (CartoDB positron will be the default base, but also explicitly added for control)
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

    # Process and add included brunnels to map (metrics already collected)
    for brunnel in brunnels.values():
        brunnel_coords = [[pos.latitude, pos.longitude] for pos in brunnel.coords]
        if not brunnel_coords:
            continue

        brunnel_type = brunnel.brunnel_type
        exclusion_reason = brunnel.exclusion_reason
        route_span = brunnel.get_route_span()

        # Display included brunnels and "not nearest" excluded brunnels
        if exclusion_reason not in [ExclusionReason.NONE, ExclusionReason.NOT_NEAREST]:
            continue

        # Set color and style based on inclusion status
        if exclusion_reason == ExclusionReason.NONE:
            # Included brunnels with 80% saturation
            opacity = 0.9
            weight = 4
            if brunnel_type == BrunnelType.BRIDGE:
                color = "#D23C4C"  # Included Bridges (80% saturation)
            else:  # TUNNEL
                color = "#69498F"  # Included Tunnels (80% saturation)
        else:  # NOT_NEAREST
            # Not nearest brunnels with lighter colors
            opacity = 0.6
            weight = 3
            if brunnel_type == BrunnelType.BRIDGE:
                color = "#DF94A7"  # Not Nearest Bridges (lighter)
            else:  # TUNNEL
                color = "#B495C2"  # Not Nearest Tunnels (lighter)

        # Create popup text with full metadata
        if exclusion_reason == ExclusionReason.NONE:
            if route_span:
                status = (
                    f"{route_span.start_distance:.2f} - {route_span.end_distance:.2f} km; "
                    f"length: {route_span.end_distance - route_span.start_distance:.2f} km"
                )
            else:
                status = "included (reason: none)"
        else:  # NOT_NEAREST
            status = "not nearest among overlapping brunnels"

        popup_header = f"<b>{brunnel_type.value.capitalize()}</b> ({status})<br>"

        metadata_html = brunnel_to_html(brunnel)
        popup_text = popup_header + metadata_html

        # Style and add brunnel based on type
        if brunnel_type == BrunnelType.TUNNEL:
            folium.PolyLine(
                brunnel_coords,
                color=color,
                weight=weight,
                opacity=opacity,
                popup=folium.Popup(
                    popup_text, max_width=400
                ),  # Wider for compound brunnels
                z_index=2,  # Ensure tunnels are above route
            ).add_to(route_map)
        else:
            folium.PolyLine(
                brunnel_coords,
                color=color,
                weight=weight,
                opacity=opacity,
                popup=folium.Popup(
                    popup_text, max_width=400
                ),  # Wider for compound brunnels
                z_index=2,  # Ensure bridges are above route
            ).add_to(route_map)

    # Add legend with dynamic counts from metrics
    legend = BrunnelLegend(metrics)
    route_map.add_child(legend)

    # Fit map bounds to buffered route area
    bounds = [[south, west], [north, east]]  # Southwest corner  # Northeast corner
    route_map.fit_bounds(bounds)

    route_map.save(output_filename)

    logger.debug(
        f"Map saved to {output_filename} with {metrics.bridge_counts.get('contained', 0)}/{metrics.bridge_counts.get('total', 0)} bridges and {metrics.tunnel_counts.get('contained', 0)}/{metrics.tunnel_counts.get('total', 0)} tunnels contained in route buffer"
    )
