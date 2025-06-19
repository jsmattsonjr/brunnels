from typing import Dict, Any, Tuple, List
import requests
import logging
import argparse
import time


DEFAULT_API_TIMEOUT = 30
OVERPASS_API_URL = "https://overpass-api.de/api/interpreter"

# Configure logging
logger = logging.getLogger(__name__)


def query_overpass_brunnels(
    bbox: Tuple[float, float, float, float],
    args: argparse.Namespace,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Query Overpass API for bridge and tunnel ways within bounding box with cycling-relevant filtering.

    Retries up to 3 times with exponential backoff on 429 (rate limit) errors.

    Returns:
        Tuple of (bridges, tunnels) as separate lists

    Raises:
        requests.exceptions.RequestException: On network or HTTP errors after retries
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

    # Retry with exponential backoff for 429 errors
    attempt = 0
    max_retries = 5  # Increased for CI environments
    base_delay = 2.0  # Longer initial delay for CI

    while True:
        try:
            response = requests.post(
                url, data=query.strip(), timeout=DEFAULT_API_TIMEOUT
            )
            response.raise_for_status()

            elements = response.json().get("elements", [])
            return _parse_separated_results(elements)

        except requests.exceptions.HTTPError as e:
            status_code = e.response.status_code if e.response else None
            logger.debug(
                f"HTTPError caught: status={status_code}, attempt={attempt}, max_retries={max_retries}"
            )
            logger.debug(f"Exception message: {str(e)}")
            logger.debug(f"Response object: {e.response}")
            if e.response:
                logger.debug(
                    f"Response status_code attribute: {getattr(e.response, 'status_code', 'MISSING')}"
                )
                logger.debug(f"Response type: {type(e.response)}")

            # Check if this is a retryable error (429 rate limit or 5xx server errors)
            is_retryable = False
            if e.response and hasattr(e.response, "status_code"):
                # 429 rate limit or 5xx server errors
                is_retryable = (
                    e.response.status_code == 429 or e.response.status_code >= 500
                )
            else:
                # Fallback: check exception message for retryable errors
                error_msg = str(e).lower()
                is_retryable = any(
                    code in error_msg for code in ["429", "500", "502", "503", "504"]
                )

            if is_retryable and attempt < max_retries:
                # Calculate delay with exponential backoff
                delay = base_delay * (2**attempt)
                error_type = (
                    "Server error"
                    if status_code and status_code >= 500
                    else "Rate limited"
                )
                logger.warning(
                    f"{error_type} ({status_code or 'unknown'}), retrying in {delay:.0f}s (attempt {attempt + 1} of {max_retries + 1})"
                )
                time.sleep(delay)
                attempt += 1
                continue
            else:
                # Re-raise for non-retryable errors or final attempt
                logger.debug(
                    f"Not retrying: status={status_code}, attempt={attempt}, max_retries={max_retries}"
                )
                raise


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
