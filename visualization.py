#!/usr/bin/env python3
"""
Route visualization using folium maps.
"""

from typing import List, Optional
import logging
import folium
from models import Position
from overpass import BrunnelWay, BrunnelType

logger = logging.getLogger(__name__)


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

    # Add bridges and tunnels
    bridge_count = 0
    tunnel_count = 0

    for brunnel in brunnels:
        if not brunnel.coords:
            continue

        # Convert brunnel coordinates for folium
        brunnel_coords = [[pos.latitude, pos.longitude] for pos in brunnel.coords]

        # Style and add brunnel based on type
        if brunnel.brunnel_type == BrunnelType.BRIDGE:
            bridge_count += 1
            folium.PolyLine(
                brunnel_coords,
                color="blue",
                weight=2,
                opacity=0.7,
                popup=f"Bridge (OSM ID: {brunnel.metadata.get('id', 'unknown')})",
            ).add_to(route_map)
        else:  # TUNNEL
            tunnel_count += 1
            folium.PolyLine(
                brunnel_coords,
                color="purple",
                weight=2,
                opacity=0.7,
                dash_array="5, 5",
                popup=f"Tunnel (OSM ID: {brunnel.metadata.get('id', 'unknown')})",
            ).add_to(route_map)

    # Add legend as HTML overlay by post-processing the saved file
    legend_html = f"""
    <div style='position: fixed; bottom: 50px; left: 50px; width: 150px; height: 110px; 
                background-color: white; border: 2px solid grey; z-index: 9999; 
                font-size: 14px; padding: 10px; font-family: Arial, sans-serif;'>
        <b>Legend</b><br>
        <span style='color: red; font-weight: bold;'>—</span> GPX Route<br>
        <span style='color: blue; font-weight: bold;'>—</span> Bridges ({bridge_count})<br>
        <span style='color: purple; font-weight: bold;'>- -</span> Tunnels ({tunnel_count})
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
        f"Map saved to {output_filename} with {bridge_count} bridges and {tunnel_count} tunnels"
    )
