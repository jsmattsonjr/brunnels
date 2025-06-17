from typing import Dict, Any, Tuple, List
import requests
import logging
import argparse


DEFAULT_API_TIMEOUT = 30
OVERPASS_API_URL = "https://overpass-api.de/api/interpreter"

# Configure logging
logger = logging.getLogger(__name__)


def query_overpass_brunnels(
    bbox: Tuple[float, float, float, float],
    args: argparse.Namespace,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Query Overpass API for bridge and tunnel ways within bounding box with cycling-relevant filtering.

    Returns:
        Tuple of (bridges, tunnels) as separate lists
    """
    south, west, north, east = bbox

    base_filters = ""

    if not args.include_waterways:
        base_filters += "[!waterway]"

    if not args.include_bicycle_no:
        base_filters += '["bicycle"!="no"]'

    railway_filter = ""
    if not args.include_active_railways:
        railway_filter = ' && (!t["railway"] || t["railway"] == "abandoned")'

    # Overpass QL query with count separators to distinguish bridges from tunnels
    query = f"""
[out:json][timeout:{DEFAULT_API_TIMEOUT}][bbox:{south},{west},{north},{east}];
way[bridge]{base_filters}(if:!is_closed(){railway_filter});
out count;
out geom qt;
way[tunnel]{base_filters}(if:!is_closed(){railway_filter});
out count;
out geom qt;
"""

    url = OVERPASS_API_URL

    response = requests.post(url, data=query.strip(), timeout=DEFAULT_API_TIMEOUT)
    response.raise_for_status()

    elements = response.json().get("elements", [])
    return _parse_separated_results(elements)


def _parse_separated_results(
    elements: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Parse Overpass response with count separators into bridges and tunnels.

    Args:
        elements: Raw elements from Overpass response

    Returns:
        Tuple of (bridges, tunnels) as separate lists
    """
    bridges = []
    tunnels = []
    current_type = None

    for element in elements:
        if element["type"] == "count":
            # First count is bridges, second count is tunnels
            current_type = "tunnel" if current_type == "bridge" else "bridge"
            logger.debug(f"Found {element['tags']['total']} {current_type}")
        elif element["type"] == "way":
            if current_type == "bridge":
                bridges.append(element)
            elif current_type == "tunnel":
                tunnels.append(element)
            else:
                # Fallback: shouldn't happen with our query structure
                logger.warning(
                    f"Found way {element.get('id')} before any count element"
                )

    logger.debug(
        f"Parsed {len(bridges)} bridges and {len(tunnels)} tunnels from Overpass response"
    )
    return bridges, tunnels
