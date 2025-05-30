#!/usr/bin/env python3
"""
Route visualization using folium maps.
"""

from typing import List
import logging
import folium
from models import Position

logger = logging.getLogger(__name__)


def create_route_map(route: List[Position], output_filename: str) -> None:
    """
    Create an interactive map showing the route and save as HTML.

    Args:
        route: List of Position objects representing the route
        output_filename: Path where HTML map file should be saved

    Raises:
        ValueError: If route is empty
    """
    if not route:
        raise ValueError("Cannot create map for empty route")

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

    # Save map
    route_map.save(output_filename)
    logger.info(f"Map saved to {output_filename}")
