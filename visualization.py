#!/usr/bin/env python3
"""
Route visualization using folium maps.
"""

from typing import List, Optional, Dict, Any
import logging
import folium
from models import Position, BrunnelWay, BrunnelType, FilterReason

logger = logging.getLogger(__name__)


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

    # Add other metadata (excluding tags and id which we already handled)
    other_data = {k: v for k, v in metadata.items() if k not in ["tags", "id"]}
    if other_data:
        html_parts.append("<br><b>Other:</b>")
        for key, value in sorted(other_data.items()):
            # Handle nested dictionaries or lists
            if isinstance(value, (dict, list)):
                value_str = str(value)
                if len(value_str) > 50:  # Truncate very long values
                    value_str = value_str[:47] + "..."
            else:
                value_str = str(value)
            html_parts.append(f"<br>&nbsp;&nbsp;<i>{key}:</i> {value_str}")

    return "".join(html_parts)


def create_route_map(
    route: List[Position],
    output_filename: str,
    brunnels: Optional[List[BrunnelWay]] = None,
) -> None:
    """
    Create an interactive map showing the route and nearby bridges/tunnels, save as HTML.

    Args:
        route: List of Position objects representing the route
        output_filename: Path where HTML map file should be saved
        brunnels: Optional list of BrunnelWay objects to display on map

    Raises:
        ValueError: If route is empty
    """
    if not route:
        raise ValueError("Cannot create map for empty route")

    if brunnels is None:
        brunnels = []

    # Calculate map center from route bounds
    latitudes = [pos.latitude for pos in route]
    longitudes = [pos.longitude for pos in route]

    center_lat = (min(latitudes) + max(latitudes)) / 2
    center_lon = (min(longitudes) + max(longitudes)) / 2

    logger.info(f"Creating map centered at ({center_lat:.4f}, {center_lon:.4f})")

    # Create map with CartoDB Positron tiles
    route_map = folium.Map(
        location=[center_lat, center_lon], zoom_start=10, tiles="CartoDB positron"
    )

    # Convert route to coordinate pairs for folium
    coordinates = [[pos.latitude, pos.longitude] for pos in route]

    # Add route as polyline
    folium.PolyLine(
        coordinates, color="red", weight=3, opacity=0.8, popup="GPX Route"
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
            opacity = 0.7
            if brunnel.brunnel_type == BrunnelType.BRIDGE:
                color = "blue"
                contained_bridge_count += 1
            else:  # TUNNEL
                color = "brown"
                contained_tunnel_count += 1
        else:
            # Use muted colors for filtered or non-contained brunnels
            opacity = 0.3
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
        if brunnel.brunnel_type == BrunnelType.TUNNEL and brunnel.contained_in_route:
            # Use dashed line for contained tunnels
            folium.PolyLine(
                brunnel_coords,
                color=color,
                weight=2,
                opacity=opacity,
                dash_array="5, 5",
                popup=folium.Popup(popup_text, max_width=300),
            ).add_to(route_map)
        else:
            # Solid line for bridges and non-contained tunnels
            folium.PolyLine(
                brunnel_coords,
                color=color,
                weight=2,
                opacity=opacity,
                popup=folium.Popup(popup_text, max_width=300),
            ).add_to(route_map)

    # Add legend as HTML overlay by post-processing the saved file
    legend_html = f"""
    <div style='position: fixed; bottom: 50px; left: 50px; width: 200px; height: 150px; 
                background-color: white; border: 2px solid grey; z-index: 9999; 
                font-size: 14px; padding: 10px; font-family: Arial, sans-serif;'>
        <b>Legend</b><br>
        <span style='color: red; font-weight: bold;'>—</span> GPX Route<br>
        <span style='color: blue; font-weight: bold;'>—</span> Bridges ({contained_bridge_count}/{bridge_count})<br>
        <span style='color: brown; font-weight: bold;'>- -</span> Tunnels ({contained_tunnel_count}/{tunnel_count})<br>
        <span style='color: lightsteelblue; font-weight: bold;'>—</span> Non-contained/filtered
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
    logger.info(
        f"Map saved to {output_filename} with {contained_bridge_count}/{bridge_count} bridges and {contained_tunnel_count}/{tunnel_count} tunnels contained in route buffer"
    )
