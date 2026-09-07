"""Biketerra brunnels server interface.

The Biketerra server takes the route polyline itself rather than a bounding box,
and returns Overpass-shaped `way` elements for the bridges and tunnels along it.
Because it filters against the route corridor server-side, it returns far less
data than the equivalent Overpass bounding-box query, and it does not rate-limit
the way the public Overpass instance does.
"""

from typing import Any, Dict, List, Sequence, Tuple
import argparse
import logging
import time

import requests

from brunnels import __version__
from .geometry import Position
from .overpass import _is_retryable_error

BIKETERRA_API_URL = "https://tiles.biketerra.com/brunnels"

# The server rejects requests with more coordinates than this, so long routes
# are split across several requests.
MAX_COORDS_PER_REQUEST = 2500

# Width of the corridor the server searches around the polyline. Measured
# empirically; a --query-buffer wider than this can't be served remotely.
SERVER_QUERY_BUFFER = 25.0

REQUEST_HEADERS = {
    "User-Agent": f"brunnels/{__version__} (https://github.com/jsmattsonjr/brunnels)",
    "Content-Type": "application/json",
}

logger = logging.getLogger(__name__)


def unsupported_options(args: argparse.Namespace) -> List[str]:
    """Return the requested options the Biketerra server cannot honor.

    The server applies brunnels' default cycling-relevance filtering (no
    waterways, no bicycle=no, no active railways) and a fixed corridor width,
    with no way to ask for anything else.
    """
    unsupported = []

    if args.include_waterways:
        unsupported.append("--include-waterways")
    if args.include_bicycle_no:
        unsupported.append("--include-bicycle-no")
    if args.include_active_railways:
        unsupported.append("--include-active-railways")
    if args.query_buffer > SERVER_QUERY_BUFFER:
        unsupported.append(f"--query-buffer greater than {SERVER_QUERY_BUFFER:.0f}")

    return unsupported


def _chunk_coords(
    coords: Sequence[Position],
) -> List[List[List[float]]]:
    """Split the route into request-sized [lat, lon] chunks.

    Consecutive chunks share a coordinate so no segment of the route falls
    between two requests.
    """
    pairs = [[coord.latitude, coord.longitude] for coord in coords]

    if len(pairs) <= MAX_COORDS_PER_REQUEST:
        return [pairs]

    chunks = []
    start = 0
    while start < len(pairs) - 1:
        end = min(start + MAX_COORDS_PER_REQUEST, len(pairs))
        chunks.append(pairs[start:end])
        start = end - 1

    return chunks


def _post_chunk(chunk: List[List[float]], timeout: int) -> List[Dict[str, Any]]:
    """POST one chunk of the polyline, retrying on rate limits and server errors."""
    attempt = 0
    max_retries = 3
    base_delay = 2.0

    while True:
        try:
            response = requests.post(
                BIKETERRA_API_URL,
                json={"coords": chunk},
                timeout=timeout,
                headers=REQUEST_HEADERS,
            )
            response.raise_for_status()
            return response.json().get("elements", [])

        except requests.exceptions.HTTPError as e:
            status_code = e.response.status_code if e.response else None

            if _is_retryable_error(e) and attempt < max_retries:
                delay = base_delay * (2**attempt)
                logger.warning(
                    f"Biketerra server error ({status_code or 'unknown'}), "
                    f"retrying in {delay:.0f}s "
                    f"(attempt {attempt + 1} of {max_retries + 1})"
                )
                time.sleep(delay)
                attempt += 1
                continue

            raise


def query_biketerra_brunnels(
    coords: Sequence[Position],
    args: argparse.Namespace,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Query the Biketerra server for bridges and tunnels along the route.

    Returns:
        Tuple of (bridges, tunnels) as separate lists of Overpass-shaped ways.
        A way tagged as both is returned in both lists, matching what the
        Overpass query does.

    Raises:
        requests.exceptions.RequestException: On network or HTTP errors after retries
    """
    chunks = _chunk_coords(coords)

    if len(chunks) > 1:
        logger.debug(
            f"Splitting {len(coords)} route points across "
            f"{len(chunks)} Biketerra requests"
        )

    ways_by_id: Dict[int, Dict[str, Any]] = {}
    for i, chunk in enumerate(chunks):
        elements = _post_chunk(chunk, args.timeout)
        logger.debug(
            f"Biketerra request {i + 1}/{len(chunks)} "
            f"({len(chunk)} points) returned {len(elements)} ways"
        )
        for element in elements:
            if element.get("type") != "way":
                continue
            ways_by_id[element["id"]] = element

    bridges = []
    tunnels = []
    for way in ways_by_id.values():
        tags = way.get("tags", {})
        if "bridge" in tags:
            bridges.append(way)
        if "tunnel" in tags:
            tunnels.append(way)
        if "bridge" not in tags and "tunnel" not in tags:
            logger.warning(
                f"Biketerra server returned way {way['id']} "
                f"tagged as neither bridge nor tunnel"
            )

    logger.debug(
        f"Biketerra server found {len(bridges)} bridges and {len(tunnels)} tunnels"
    )

    return bridges, tunnels
