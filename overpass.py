from typing import Dict, Any, Tuple, List
import requests
import logging

from brunnel_way import BrunnelWay


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


# Backwards compatibility functions with deprecation warnings
def determine_brunnel_type(metadata: Dict[str, Any]):
    """
    Backwards compatibility wrapper for BrunnelWay.determine_type().

    Args:
        metadata: OSM metadata for the brunnel

    Returns:
        BrunnelType enum value
    """
    logger.warning(
        "determine_brunnel_type() is deprecated. Use BrunnelWay.determine_type() instead."
    )
    return BrunnelWay.determine_type(metadata)


def should_filter_brunnel(metadata: Dict[str, Any], keep_polygons: bool = False):
    """
    Backwards compatibility wrapper for BrunnelWay.should_filter().

    Args:
        metadata: OSM metadata for the brunnel
        keep_polygons: If False, filter out closed ways

    Returns:
        FilterReason enum value
    """
    logger.warning(
        "should_filter_brunnel() is deprecated. Use BrunnelWay.should_filter() instead."
    )
    return BrunnelWay.should_filter(metadata, keep_polygons)


def parse_overpass_way(
    way_data: Dict[str, Any], keep_polygons: bool = False
) -> BrunnelWay:
    """
    Backwards compatibility wrapper for BrunnelWay.from_overpass_data().

    Args:
        way_data: Raw way data from Overpass API
        keep_polygons: Whether to keep closed ways

    Returns:
        BrunnelWay object
    """
    logger.warning(
        "parse_overpass_way() is deprecated. Use BrunnelWay.from_overpass_data() instead."
    )
    return BrunnelWay.from_overpass_data(way_data, keep_polygons)
