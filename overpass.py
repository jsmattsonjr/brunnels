from typing import Dict, Any, Tuple, List
import requests
import logging

from models import Position, BrunnelType, BrunnelWay
from geometry import find_intersecting_brunnels
from gpx import calculate_route_bbox


DEFAULT_API_TIMEOUT = 30
OVERPASS_API_URL = "https://overpass-api.de/api/interpreter"

# Configure logging
logger = logging.getLogger(__name__)


def determine_brunnel_type(metadata: Dict[str, Any]) -> BrunnelType:
    """Determine brunnel type from OSM metadata."""
    tags = metadata.get("tags", {})

    # Check for tunnel first (tunnels are often more specific)
    if "tunnel" in tags and tags["tunnel"] not in ["no", "false"]:
        return BrunnelType.TUNNEL

    # Otherwise, assume it's a bridge
    return BrunnelType.BRIDGE


def parse_overpass_way(way_data: Dict[str, Any]) -> BrunnelWay:
    """Parse a single way from Overpass response into BrunnelWay object."""
    # Extract coordinates from geometry
    coords = []
    if "geometry" in way_data:
        for node in way_data["geometry"]:
            coords.append(Position(latitude=node["lat"], longitude=node["lon"]))

    brunnel_type = determine_brunnel_type(way_data)

    return BrunnelWay(coords=coords, metadata=way_data, brunnel_type=brunnel_type)


def query_overpass_brunnels(
    bbox: Tuple[float, float, float, float],
) -> List[Dict[str, Any]]:
    """Query Overpass API for bridge and tunnel ways within bounding box."""
    south, west, north, east = bbox

    # Overpass QL query for both bridge and tunnel ways with geometry
    query = f"""
[out:json][timeout:25];
(
  way[bridge]({south},{west},{north},{east});
  way[tunnel]({south},{west},{north},{east});
);
out geom qt;
"""

    url = OVERPASS_API_URL

    try:
        logger.info("Querying Overpass API for bridges and tunnels...")
        response = requests.post(url, data=query.strip(), timeout=DEFAULT_API_TIMEOUT)
        response.raise_for_status()
        return response.json().get("elements", [])
    except requests.ConnectionError:
        logger.error("Network connection error. Check your internet connection.")
        return []
    except requests.Timeout:
        logger.error("API request timed out. Try again later.")
        return []
    except requests.HTTPError as e:
        logger.error(f"HTTP error {e.response.status_code}: {e}")
        return []
    except ValueError as e:  # JSON decode error
        logger.error(f"Invalid response format: {e}")
        return []


def find_route_brunnels(
    route: List[Position], buffer_km: float = 1.0
) -> List[BrunnelWay]:
    """
    Find all bridges and tunnels near the given route and check for intersections.

    Args:
        route: List of Position objects representing the route
        buffer_km: Buffer distance in kilometers to search around route

    Returns:
        List of BrunnelWay objects found near the route, with intersection status set
    """
    if not route:
        logger.warning("Cannot find brunnels for empty route")
        return []

    bbox = calculate_route_bbox(route, buffer_km)
    raw_ways = query_overpass_brunnels(bbox)

    brunnels = []
    for way_data in raw_ways:
        try:
            brunnel = parse_overpass_way(way_data)
            brunnels.append(brunnel)
        except (KeyError, ValueError) as e:
            logger.warning(f"Failed to parse brunnel way: {e}")
            continue

    logger.info(f"Found {len(brunnels)} bridges/tunnels near route")

    # Check for intersections with the route
    find_intersecting_brunnels(route, brunnels)

    return brunnels
