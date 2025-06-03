#!/usr/bin/env python3
"""
Brunnel (Bridge/Tunnel) Visualization Tool
This script processes a GPX file to find bridges and tunnels along a route,
and generates an interactive HTML map visualizing the route and the brunnels.

Requirements:
    pip install gpxpy folium requests shapely

"""

from typing import Sequence
import webbrowser
import argparse
import logging
import sys
import os
import gpxpy
import gpxpy.gpx

from . import visualization
from .route import Route, RouteValidationError
from .brunnel import Brunnel
from .compound_brunnel_way import CompoundBrunnelWay

# Configure logging
logger = logging.getLogger("brunnels")


def create_argument_parser() -> argparse.ArgumentParser:
    """
    Create and configure the command-line argument parser.

    Returns:
        Configured ArgumentParser instance
    """
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
        "--bearing-tolerance",
        type=float,
        default=20.0,
        help="Bearing alignment tolerance in degrees (default: 20.0)",
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
    parser.add_argument(
        "--keep-polygons",
        action="store_true",
        help="Keep closed ways (polygons) where first node equals last node",
    )
    parser.add_argument(
        "--no-overlap-filtering",
        action="store_true",
        help="Disable filtering of overlapping brunnels (keep all overlapping brunnels)",
    )
    parser.add_argument(
        "--no-compound-brunnels",
        action="store_true",
        help="Disable creation of compound brunnels from adjacent segments",
    )
    return parser


def open_file_in_browser(filename: str) -> None:
    """
    Open the specified file in the default browser.

    Args:
        filename: Path to the file to open
    """
    abs_path = os.path.abspath(filename)
    try:
        webbrowser.open(f"file://{abs_path}")
        logger.debug(f"Opening {abs_path} in your default browser...")
    except Exception as e:
        logger.warning(f"Could not automatically open browser: {e}")
        logger.warning(f"Please manually open {abs_path}")


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

    # Configure the root logger so all modules inherit the configuration
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.addHandler(console_handler)

    # Suppress overly verbose third-party logging
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)


def log_final_included_brunnels(brunnels: Sequence[Brunnel]) -> None:
    """
    Log the final list of brunnels that are included in the route (after all processing).
    This shows the actual brunnels that will appear on the map.

    Args:
        brunnels: Sequence of all brunnels to check (including compound brunnels)
    """
    # Find final included brunnels (those that are contained and not filtered)
    included_brunnels = [b for b in brunnels if b.contained_in_route]

    if not included_brunnels:
        logger.info("No brunnels included in final map")
        return

    # Sort by start distance along route
    included_brunnels.sort(
        key=lambda b: (b.route_span.start_distance_km if b.route_span else 0.0)
    )

    logger.info(f"Included brunnels ({len(included_brunnels)}):")
    for brunnel in included_brunnels:
        logger.info(f"  {brunnel.get_log_description()}")


def main():
    parser = create_argument_parser()
    args = parser.parse_args()

    # Setup logging
    setup_logging(args.log_level)

    # Load and parse the GPX file into a route
    try:
        route = Route.from_file(args.filename)
    except (FileNotFoundError, PermissionError) as e:
        logger.error(f"Failed to read file '{args.filename}': {e}")
        sys.exit(1)
    except gpxpy.gpx.GPXException as e:
        logger.error(f"Failed to parse GPX file: {e}")
        sys.exit(1)
    except RouteValidationError as e:
        logger.error(f"Route validation failed: {e}")
        sys.exit(1)

    logger.info(f"Loaded GPX route with {len(route)} points")

    # Find bridges and tunnels near the route (containment detection included)
    try:
        brunnels: Sequence[Brunnel] = route.find_brunnels(
            args.buffer,
            args.route_buffer,
            bearing_tolerance_degrees=args.bearing_tolerance,
            enable_tag_filtering=not args.no_tag_filtering,
            keep_polygons=args.keep_polygons,
        )
    except Exception as e:
        logger.error(f"Failed to query bridges and tunnels: {e}")
        sys.exit(1)

    # Create compound brunnels from adjacent segments
    if not args.no_compound_brunnels:
        try:
            brunnels = CompoundBrunnelWay.create_from_brunnels(brunnels)
        except Exception as e:
            logger.error(f"Failed to create compound brunnels: {e}")
            sys.exit(1)

    # Filter overlapping brunnels (keep only nearest in each overlapping group)
    if not args.no_overlap_filtering:
        try:
            route.filter_overlapping_brunnels(brunnels)
        except Exception as e:
            logger.error(f"Failed to filter overlapping brunnels: {e}")
            sys.exit(1)

    # Log the final list of included brunnels (what will actually appear on the map)
    log_final_included_brunnels(brunnels)

    # Create visualization map
    try:
        visualization.create_route_map(route, args.output, brunnels, args.buffer)
    except Exception as e:
        logger.error(f"Failed to create map: {e}")
        sys.exit(1)

    # Automatically open the HTML file in the default browser
    if not args.no_open:
        open_file_in_browser(args.output)


if __name__ == "__main__":
    main()
