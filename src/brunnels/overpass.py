from typing import Dict, Any, Tuple, List
import requests
import logging
import argparse
import time


DEFAULT_API_TIMEOUT = 30
OVERPASS_API_URL = "https://overpass-api.de/api/interpreter"

# Active railway types that are filtered out by default (unless --include-active-railways is used)
ACTIVE_RAILWAY_TYPES = [
    "rail",
    "light_rail",
    "subway",
    "tram",
    "narrow_gauge",
    "funicular",
    "monorail",
    "miniature",
    "preserved",
]

# Configure logging
logger = logging.getLogger(__name__)


def _build_base_filters(args: argparse.Namespace) -> str:
    """Build base filter string for Overpass query."""
    base_filters = ""

    if not args.include_waterways:
        base_filters += "[!waterway]"

    if not args.include_bicycle_no:
        base_filters += '["bicycle"!="no"]'

    return base_filters


def _build_railway_exclusions(
    args: argparse.Namespace, base_filters: str
) -> Tuple[str, str]:
    """Build railway exclusion strings for bridges and tunnels."""
    if args.include_active_railways:
        return "", ""

    active_railway_pattern = "|".join(ACTIVE_RAILWAY_TYPES)
    railway_exclusion = (
        f'["railway"~"^({active_railway_pattern})$"]{base_filters}(if:!is_closed());'
    )

    bridge_railway_exclusion = f"\n  - way[bridge]{railway_exclusion}"
    tunnel_railway_exclusion = f"\n  - way[tunnel]{railway_exclusion}"

    return bridge_railway_exclusion, tunnel_railway_exclusion


def _build_overpass_query(
    bbox: Tuple[float, float, float, float],
    base_filters: str,
    bridge_railway_exclusion: str,
    tunnel_railway_exclusion: str,
    timeout: int = DEFAULT_API_TIMEOUT,
) -> str:
    """Build the complete Overpass QL query string."""
    south, west, north, east = bbox

    return (
        f"[out:json][timeout:{timeout}][bbox:{south},{west},{north},{east}];\n"
        f"(\n"
        f"  (\n"
        f"    way[bridge]{base_filters}(if:!is_closed());{bridge_railway_exclusion}\n"
        f"  );\n"
        f"  way[bridge][highway=cycleway](if:!is_closed());\n"
        f");\n"
        f"out count;\n"
        f"out geom qt;\n"
        f"(\n"
        f"  (\n"
        f"    way[tunnel]{base_filters}(if:!is_closed());{tunnel_railway_exclusion}\n"
        f"  );\n"
        f"  way[tunnel][highway=cycleway](if:!is_closed());\n"
        f");\n"
        f"out count;\n"
        f"out geom qt;\n"
    )


def _is_retryable_error(e: requests.exceptions.HTTPError) -> bool:
    """Check if an HTTP error is retryable."""
    if e.response and hasattr(e.response, "status_code"):
        return e.response.status_code == 429 or e.response.status_code >= 500
    else:
        error_msg = str(e).lower()
        return any(code in error_msg for code in ["429", "500", "502", "503", "504"])


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
    base_filters = _build_base_filters(args)
    bridge_railway_exclusion, tunnel_railway_exclusion = _build_railway_exclusions(
        args, base_filters
    )
    query = _build_overpass_query(
        bbox,
        base_filters,
        bridge_railway_exclusion,
        tunnel_railway_exclusion,
        args.timeout,
    )

    url = OVERPASS_API_URL
    attempt = 0
    max_retries = 5
    base_delay = 2.0

    while True:
        try:
            response = requests.post(url, data=query.strip(), timeout=args.timeout)
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

            if _is_retryable_error(e) and attempt < max_retries:
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
            current_type = "tunnels" if current_type == "bridges" else "bridges"
            logger.debug(
                f"Overpass query found {element['tags']['total']} {current_type}s"
            )
        elif element["type"] == "way":
            if current_type == "bridges":
                bridges.append(element)
            elif current_type == "tunnels":
                tunnels.append(element)
            else:
                # Fallback: shouldn't happen with our query structure
                logger.warning(
                    f"Found way {element.get('id')} before any count element"
                )

    return bridges, tunnels
