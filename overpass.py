from typing import Dict, Any, Tuple, List
import requests
import logging
import math

from geometry import Position
from brunnel_way import BrunnelType, BrunnelWay, FilterReason


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


def should_filter_brunnel(
    metadata: Dict[str, Any], keep_polygons: bool = False
) -> FilterReason:
    """
    Determine if a brunnel should be filtered out based on cycling relevance and geometry.

    Args:
        metadata: OSM metadata for the brunnel
        keep_polygons: If False, filter out closed ways (first node == last node)

    Returns FilterReason.NONE if the brunnel should be kept, otherwise returns
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


def parse_overpass_way(
    way_data: Dict[str, Any], keep_polygons: bool = False
) -> BrunnelWay:
    """Parse a single way from Overpass response into BrunnelWay object."""
    # Extract coordinates from geometry
    coords = []
    if "geometry" in way_data:
        for node in way_data["geometry"]:
            coords.append(Position(latitude=node["lat"], longitude=node["lon"]))

    brunnel_type = determine_brunnel_type(way_data)
    filter_reason = should_filter_brunnel(way_data, keep_polygons)

    return BrunnelWay(
        coords=coords,
        metadata=way_data,
        brunnel_type=brunnel_type,
        filter_reason=filter_reason,
    )


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
