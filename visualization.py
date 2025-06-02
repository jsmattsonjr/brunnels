#!/usr/bin/env python3
"""
Route visualization using folium maps with polymorphic brunnel handling.
"""

from typing import List, Dict, Any, Union, Sequence
import logging
import folium
from brunnel_way import BrunnelWay, BrunnelType, FilterReason
from compound_brunnel_way import CompoundBrunnelWay
from route import Route

logger = logging.getLogger(__name__)

# Type alias for brunnel objects
BrunnelLike = Union[BrunnelWay, CompoundBrunnelWay]


def create_route_map(
    route: Route,
    output_filename: str,
    brunnels: Sequence[BrunnelLike],
    buffer_km: float,
) -> None:
    """
    Create an interactive map showing the route and nearby bridges/tunnels, save as HTML.

    Args:
        route: Route object representing the route
        output_filename: Path where HTML map file should be saved
        brunnels: Sequence of BrunnelWay or CompoundBrunnelWay objects to display on map
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

    # Convert route to coordinate pairs for folium using the new method
    coordinates = route.get_visualization_coordinates()

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
        # Use polymorphic interface - all brunnels have these properties
        brunnel_coords = brunnel.get_visualization_coordinates()
        if not brunnel_coords:
            continue

        brunnel_type = brunnel.brunnel_type
        contained = brunnel.contained_in_route
        filter_reason = brunnel.filter_reason
        route_span = brunnel.route_span

        # Determine color and opacity based on containment status and filtering
        if contained:
            opacity = 0.9
            weight = 4
            if brunnel_type == BrunnelType.BRIDGE:
                color = "blue"
                contained_bridge_count += 1
            else:  # TUNNEL
                color = "brown"
                contained_tunnel_count += 1
        else:
            # Use muted colors for filtered or non-contained brunnels
            opacity = 0.3
            weight = 2
            if brunnel_type == BrunnelType.BRIDGE:
                color = "lightsteelblue"  # grey-blue for bridges
            else:  # TUNNEL
                color = "rosybrown"  # grey-brown for tunnels

        # Count all brunnels
        if brunnel_type == BrunnelType.BRIDGE:
            bridge_count += 1
        else:
            tunnel_count += 1

        # Create popup text with full metadata
        if contained:
            if route_span:
                status = (
                    f"{route_span.start_distance_km:.2f} - {route_span.end_distance_km:.2f} km; "
                    f"length: {route_span.length_km:.2f} km"
                )
            else:
                status = "contained in route buffer"
        elif filter_reason == FilterReason.NOT_CONTAINED:
            status = "not contained in route buffer"
        else:
            status = f"filtered: {filter_reason}"

        popup_header = f"<b>{brunnel_type.value.capitalize()}</b> ({status})<br>"

        # Use polymorphic to_html() method - both classes implement this
        metadata_html = brunnel.to_html()
        popup_text = popup_header + metadata_html

        # Style and add brunnel based on type
        if brunnel_type == BrunnelType.TUNNEL:
            # Use dashed line for ALL tunnels (both contained and non-contained)
            folium.PolyLine(
                brunnel_coords,
                color=color,
                weight=weight,
                opacity=opacity,
                dash_array="5, 5",
                popup=folium.Popup(
                    popup_text, max_width=400
                ),  # Wider for compound brunnels
                z_index=2,  # Ensure tunnels are above route
            ).add_to(route_map)
        else:
            # Solid line for all bridges
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
