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
) -> List[Dict[str, Any]]:
    """Query Overpass API for bridge and tunnel ways within bounding box with cycling-relevant filtering."""
    south, west, north, east = bbox

    base_filters = ""

    if not args.include_waterways:
        base_filters += "[!waterway]"

    if not args.include_bicycle_no:
        base_filters += '["bicycle"!="no"]'

    railway_filter = ""
    if not args.include_active_railways:
        railway_filter = ' && (!t["railway"] || t["railway"] == "abandoned")'

    # Overpass QL query with metadata filtering applied server-side
    query = f"""
[out:json][timeout:{DEFAULT_API_TIMEOUT}][bbox:{south},{west},{north},{east}];
(
way[bridge]{base_filters}(if:!is_closed(){railway_filter});
way[tunnel]{base_filters}(if:!is_closed(){railway_filter});
);
out geom qt;
"""

    url = OVERPASS_API_URL

    response = requests.post(url, data=query.strip(), timeout=DEFAULT_API_TIMEOUT)
    response.raise_for_status()
    return response.json().get("elements", [])
