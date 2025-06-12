from typing import Dict, Any, Tuple, List
import requests
import logging


DEFAULT_API_TIMEOUT = 30
OVERPASS_API_URL = "https://overpass-api.de/api/interpreter"

# Configure logging
logger = logging.getLogger(__name__)


def query_overpass_brunnels(
    bbox: Tuple[float, float, float, float],
) -> List[Dict[str, Any]]:
    """Query Overpass API for bridge and tunnel ways within bounding box with cycling-relevant filtering."""
    south, west, north, east = bbox

    # Overpass QL query with metadata filtering applied server-side
    # This filters out closed ways, non-cycling infrastructure, waterways, and active railways
    query = f"""
[out:json][timeout:{DEFAULT_API_TIMEOUT}][bbox:{south},{west},{north},{east}];
(
way[bridge][!waterway]["bicycle"!="no"](if:!is_closed() && (!t["railway"] || t["railway"] == "abandoned"));
way[tunnel][!waterway]["bicycle"!="no"](if:!is_closed() && (!t["railway"] || t["railway"] == "abandoned"));
);
out geom qt;
"""

    url = OVERPASS_API_URL

    response = requests.post(url, data=query.strip(), timeout=DEFAULT_API_TIMEOUT)
    response.raise_for_status()
    return response.json().get("elements", [])
