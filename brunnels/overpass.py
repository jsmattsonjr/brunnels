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
