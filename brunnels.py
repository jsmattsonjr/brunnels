#!/usr/bin/env python3
"""
Brunnel (Bridge/Tunnel) Visualization Tool
This script processes a GPX file to find bridges and tunnels along a route,
and generates an interactive HTML map visualizing the route and the brunnels.

Requirements:
    pip install gpxpy folium requests shapely tqdm

"""


import webbrowser
import argparse
import logging
import sys
import os
import gpxpy
import gpxpy.gpx

import gpx
import visualization
import overpass
from models import BrunnelType

# Configure logging
logger = logging.getLogger(__name__)


def setup_logging(log_level: str) -> None:
    """Setup logging configuration."""
    level = getattr(logging, log_level)

    # Create formatter
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s", datefmt="%H:%M:%S"
    )

    # Create console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)

    # Configure logger
    logger.setLevel(level)
    logger.addHandler(console_handler)

    # Suppress overly verbose third-party logging
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)


def main():
    parser = argparse.ArgumentParser(
        description="Brunnel (Bridge/Tunnel) visualization tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "filename",
        type=str,
        help="GPX file to process (use '-' for stdin)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="brunnel_map.html",
        help="Output HTML map file (default: brunnel_map.html)",
    )
    parser.add_argument(
        "--buffer",
        type=float,
        default=0.1,
        help="Search buffer around route in kilometers (default: 0.1)",
    )
    parser.add_argument(
        "--route-buffer",
        type=float,
        default=3.0,
        help="Route buffer for containment detection in meters (default: 3.0)",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Set logging level (default: INFO)",
    )
    parser.add_argument(
        "--no-open",
        action="store_true",
        help="Don't automatically open the HTML file in browser",
    )
    parser.add_argument(
        "--no-tag-filtering",
        action="store_true",
        help="Disable tag-based filtering for cycling relevance",
    )
    args = parser.parse_args()

    # Setup logging
    setup_logging(args.log_level)

    # Load and parse the GPX file into a route
    try:
        route = gpx.load_gpx_route(args.filename)
    except (FileNotFoundError, PermissionError) as e:
        logger.error(f"Failed to read file '{args.filename}': {e}")
        sys.exit(1)
    except gpxpy.gpx.GPXException as e:
        logger.error(f"Failed to parse GPX file: {e}")
        sys.exit(1)
    except gpx.RouteValidationError as e:
        logger.error(f"Route validation failed: {e}")
        sys.exit(1)

    logger.info(f"Loaded GPX route with {len(route)} points")

    # Find bridges and tunnels near the route (containment detection included)
    try:
        brunnels = overpass.find_route_brunnels(
            route,
            args.buffer,
            args.route_buffer,
            enable_tag_filtering=not args.no_tag_filtering,
        )
    except Exception as e:
        logger.error(f"Failed to query bridges and tunnels: {e}")
        sys.exit(1)

    # Count contained vs total brunnels
    bridges = [b for b in brunnels if b.brunnel_type == BrunnelType.BRIDGE]
    tunnels = [b for b in brunnels if b.brunnel_type == BrunnelType.TUNNEL]
    contained_bridges = [b for b in bridges if b.contained_in_route]
    contained_tunnels = [b for b in tunnels if b.contained_in_route]

    logger.info(
        f"Found {len(contained_bridges)}/{len(bridges)} contained bridges and {len(contained_tunnels)}/{len(tunnels)} contained tunnels"
    )

    # Log included brunnels before visualization
    included_brunnels = [b for b in brunnels if b.contained_in_route]
    if included_brunnels:
        # Sort by start km
        included_brunnels.sort(
            key=lambda b: b.route_span.start_distance_km if b.route_span else 0.0
        )

        logger.info("Included brunnels:")
        for brunnel in included_brunnels:
            brunnel_type = brunnel.brunnel_type.value.capitalize()
            name = brunnel.metadata.get("tags", {}).get("name", "unnamed")
            osm_id = brunnel.metadata.get("id", "unknown")

            if brunnel.route_span:
                span_data = f"{brunnel.route_span.start_distance_km:.2f}-{brunnel.route_span.end_distance_km:.2f} km (length: {brunnel.route_span.length_km:.2f} km)"
            else:
                span_data = "no span data"

            logger.info(f"{brunnel_type}: {name} ({osm_id}) {span_data}")

    # Create visualization map
    try:
        visualization.create_route_map(route, args.output, brunnels, args.buffer)
    except Exception as e:
        logger.error(f"Failed to create map: {e}")
        sys.exit(1)

    logger.info(f"Map saved to {args.output}")

    # Automatically open the HTML file in the default browser
    if not args.no_open:
        abs_path = os.path.abspath(args.output)
        try:
            webbrowser.open(f"file://{abs_path}")
            logger.info(f"Opening {abs_path} in your default browser...")
        except Exception as e:
            logger.warning(f"Could not automatically open browser: {e}")
            logger.info(f"Please manually open {abs_path}")


if __name__ == "__main__":
    main()
