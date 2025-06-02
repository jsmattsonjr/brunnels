#!/usr/bin/env python3
"""
Route visualization using folium maps.
"""

from typing import List, Dict, Any
import logging
import folium
from brunnel_way import BrunnelWay, BrunnelType, FilterReason
from route import Route

logger = logging.getLogger(__name__)


def _format_complex_value(key: str, value: Any, indent_level: int = 0) -> str:
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
                parts.append(_format_complex_value(k, v, indent_level + 1))
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
                parts.append(_format_complex_value(f"[{i}]", item, indent_level + 1))
            else:
                nested_indent = "&nbsp;" * ((indent_level + 1) * 4)
                parts.append(f"{nested_indent}[{i}]: {item}")
        return "<br>".join(parts)

    else:
        return f"{indent}<i>{key}:</i> {value}"


def _format_metadata_for_popup(metadata: Dict[str, Any]) -> str:
    """
    Format OSM metadata into HTML for popup display.

    Args:
        metadata: Dictionary containing OSM metadata

    Returns:
        HTML-formatted string with metadata
    """
    html_parts = []
    tags = metadata.get("tags", {})

    # Add name most prominently if present
    if "name" in tags:
        html_parts.append(f"<b>{tags['name']}</b>")

    # Add alt_name next if present
    if "alt_name" in tags:
        html_parts.append(f"<br><b>AKA:</b> {tags['alt_name']}")

    # Add OSM ID
    osm_id = metadata.get("id", "unknown")
    html_parts.append(f"<br><b>OSM ID:</b> {osm_id}")

    # Add remaining OSM tags (excluding name and alt_name which we already showed)
    remaining_tags = {k: v for k, v in tags.items() if k not in ["name", "alt_name"]}
    if remaining_tags:
        html_parts.append("<br><b>Tags:</b>")
        for key, value in sorted(remaining_tags.items()):
            html_parts.append(f"<br>&nbsp;&nbsp;<i>{key}:</i> {value}")

    # Add other metadata (excluding tags and id which we already handled, geometry, which is very long, and type, which is always "way")
    other_data = {
        k: v for k, v in metadata.items() if k not in ["tags", "id", "geometry", "type"]
    }
    if other_data:
        html_parts.append("<br><b>Other:</b>")
        for key, value in sorted(other_data.items()):
            # Handle nested dictionaries or lists
            if isinstance(value, (dict, list)):
                # Use structured formatting for nodes and bounds
                if key in ["nodes", "bounds"]:
                    formatted_value = _format_complex_value(key, value, 0)
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
    brunnels: List[BrunnelWay],
    buffer_km: float,
) -> None:
    """
    Create an interactive map showing the route and nearby bridges/tunnels, save as HTML.

    Args:
        route: Route object representing the route
        output_filename: Path where HTML map file should be saved
        brunnels: Optional list of BrunnelWay objects to display on map
        buffer_km: Buffer distance in kilometers for map bounds (default: 1.0)

    Raises:
        ValueError: If route is empty
    """
    if not route:
        raise ValueError("Cannot create map for empty route")

    # Calculate buffered bounding box using existing function
    south, west, north, east = route.get_bbox(buffer_km)

    center_lat = (south + north) / 2
    center_lon = (west + east) / 2

    logger.debug(f"Creating map centered at ({center_lat:.4f}, {center_lon:.4f})")

    # Create map with initial center (zoom will be set by fit_bounds)
    route_map = folium.Map(location=[center_lat, center_lon], tiles="CartoDB positron")

    # Convert route to coordinate pairs for folium
    coordinates = [[pos.latitude, pos.longitude] for pos in route]

    # Add route as polyline
    folium.PolyLine(
        coordinates, color="red", weight=2, opacity=0.6, popup="GPX Route", z_index=1
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

    # Count brunnels by type and containment status
    bridge_count = 0
    tunnel_count = 0
    contained_bridge_count = 0
    contained_tunnel_count = 0

    for brunnel in brunnels:
        if not brunnel.coords:
            continue

        # Convert brunnel coordinates for folium
        brunnel_coords = [[pos.latitude, pos.longitude] for pos in brunnel.coords]

        # Determine color and opacity based on containment status and filtering
        if brunnel.contained_in_route:
            opacity = 0.9
            weight = 4
            if brunnel.brunnel_type == BrunnelType.BRIDGE:
                color = "blue"
                contained_bridge_count += 1
            else:  # TUNNEL
                color = "brown"
                contained_tunnel_count += 1
        else:
            # Use muted colors for filtered or non-contained brunnels
            opacity = 0.3
            weight = 2
            if brunnel.brunnel_type == BrunnelType.BRIDGE:
                color = "lightsteelblue"  # grey-blue for bridges
            else:  # TUNNEL
                color = "rosybrown"  # grey-brown for tunnels

        # Count all brunnels
        if brunnel.brunnel_type == BrunnelType.BRIDGE:
            bridge_count += 1
        else:
            tunnel_count += 1

        # Create popup text with full metadata
        if brunnel.contained_in_route:
            if brunnel.route_span:
                span = brunnel.route_span
                status = (
                    f"{span.start_distance_km:.2f} - {span.end_distance_km:.2f} km; "
                    f"length: {span.length_km:.2f} km"
                )
            else:
                status = "contained in route buffer"
        elif brunnel.filter_reason == FilterReason.NOT_CONTAINED:
            status = "not contained in route buffer"
        else:
            status = f"filtered: {brunnel.filter_reason}"

        popup_header = (
            f"<b>{brunnel.brunnel_type.value.capitalize()}</b> ({status})<br>"
        )

        metadata_html = _format_metadata_for_popup(brunnel.metadata)
        popup_text = popup_header + metadata_html

        # Style and add brunnel based on type
        if brunnel.brunnel_type == BrunnelType.TUNNEL:
            # Use dashed line for ALL tunnels (both contained and non-contained)
            folium.PolyLine(
                brunnel_coords,
                color=color,
                weight=weight,
                opacity=opacity,
                dash_array="5, 5",
                popup=folium.Popup(popup_text, max_width=300),
                z_index=2,  # Ensure tunnels are above route
            ).add_to(route_map)
        else:
            # Solid line for all bridges
            folium.PolyLine(
                brunnel_coords,
                color=color,
                weight=weight,
                opacity=opacity,
                popup=folium.Popup(popup_text, max_width=300),
                z_index=2,  # Ensure bridges are above route
            ).add_to(route_map)

    # Fit map bounds to buffered route area
    bounds = [[south, west], [north, east]]  # Southwest corner  # Northeast corner
    route_map.fit_bounds(bounds)

    # Add legend as HTML overlay by post-processing the saved file
    legend_html = f"""
    <div style='position: fixed; bottom: 50px; left: 50px; width: 220px; height: 170px; 
                background-color: white; border: 2px solid grey; z-index: 9999; 
                font-size: 14px; padding: 10px; font-family: Arial, sans-serif;'>
        <b>Legend</b><br>
        <span style='color: red; font-weight: bold;'>—</span> GPX Route<br>
        <span style='color: blue; font-weight: bold;'>—</span> Included Bridges ({contained_bridge_count})<br>
        <span style='color: brown; font-weight: bold;'>- -</span> Included Tunnels ({contained_tunnel_count})<br>
        <span style='color: lightsteelblue; font-weight: bold;'>—</span> Excluded Bridges ({bridge_count - contained_bridge_count})<br>
        <span style='color: rosybrown; font-weight: bold;'>- -</span> Excluded Tunnels ({tunnel_count - contained_tunnel_count})
    </div>
    """

    # Save map first
    route_map.save(output_filename)

    # Read the saved HTML file and inject legend
    with open(output_filename, "r", encoding="utf-8") as f:
        html_content = f.read()

    # Insert legend before closing body tag
    html_content = html_content.replace("</body>", legend_html + "</body>")

    # Write back the modified HTML
    with open(output_filename, "w", encoding="utf-8") as f:
        f.write(html_content)
    logger.debug(
        f"Map saved to {output_filename} with {contained_bridge_count}/{bridge_count} bridges and {contained_tunnel_count}/{tunnel_count} tunnels contained in route buffer"
    )
