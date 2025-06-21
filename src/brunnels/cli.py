#!/usr/bin/env python3
"""
Brunnel (Bridge/Tunnel) Visualization Tool
This script processes a GPX file to find bridges and tunnels along a route,
and generates an interactive HTML map visualizing the route and the brunnels.

Requirements:
    pip install gpxpy folium requests shapely pyproj

"""

from typing import Dict, Optional
import webbrowser
import argparse
import logging
import sys
import os
import gpxpy
from gpxpy import gpx
from shapely.geometry.base import BaseGeometry


from . import __version__
from . import visualization
from .metrics import collect_metrics, log_metrics
from .route import Route
from .brunnel import (
    Brunnel,
    BrunnelType,
    ExclusionReason,
    RouteSpan,
    find_compound_brunnels,
)
from .file_utils import generate_output_filename

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
        nargs="?",
        help="GPX file to process",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output HTML map file (default: auto-generated based on input filename)",
    )
    parser.add_argument(
        "--bbox-buffer",
        type=float,
        default=10,
        help="Search buffer around route in meters (default: 10)",
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
        default="WARNING",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Set logging level (default: WARNING)",
    )
    parser.add_argument(
        "--no-open",
        action="store_true",
        help="Don't automatically open the HTML file in browser",
    )
    parser.add_argument(
        "--no-overlap-exclusion",
        action="store_true",
        help="Disable exclusion of overlapping brunnels (keep all overlapping brunnels)",
    )
    parser.add_argument(
        "--metrics",
        action="store_true",
        help="Output structured metrics after processing",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"brunnels {__version__}",
    )
    parser.add_argument(
        "--include-bicycle-no",
        action="store_true",
        help="Include ways tagged bicycle=no in the Overpass query",
    )
    parser.add_argument(
        "--include-waterways",
        action="store_true",
        help="Include ways tagged waterway in the Overpass query",
    )
    parser.add_argument(
        "--include-active-railways",
        action="store_true",
        help="Include ways tagged railway (excluding inactive types: abandoned, dismantled, disused, historic, razed, removed)",
    )
    return parser


def determine_output_filename(input_filename: str, output_arg: Optional[str]) -> str:
    """
    Determine the output filename to use.

    Args:
        input_filename: Path to the input GPX file
        output_arg: Value from --output argument (None if not specified)

    Returns:
        Output filename to use

    Raises:
        RuntimeError: If auto-generation fails
        ValueError: If constructed filename would be illegal
    """
    if output_arg is not None:
        # User specified an output filename explicitly
        return output_arg

    # Auto-generate based on input filename
    try:
        return generate_output_filename(input_filename)
    except (RuntimeError, ValueError) as e:
        logger.error(f"Failed to generate output filename: {e}")
        raise


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


def setup_logging(args: argparse.Namespace) -> None:
    """Setup logging configuration."""
    if hasattr(sys.stdout, "reconfigure") and sys.stdout.encoding != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            # Also reconfigure stderr for completeness, though the error was on stdout
            if hasattr(sys.stderr, "reconfigure") and sys.stderr.encoding != "utf-8":
                sys.stderr.reconfigure(encoding="utf-8")
            logger.debug("Reconfigured stdout and stderr to UTF-8 encoding.")
        except Exception as e:
            logger.debug(f"Could not reconfigure stdout/stderr to UTF-8: {e}")
    level = getattr(logging, args.log_level)

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


def log_nearby_brunnels(brunnels: Dict[str, Brunnel]) -> None:
    """
    Print all nearby brunnels (included, misaligned, and alternatives from overlap groups).
    Shows detailed analysis of what was found and why some were excluded.

    Args:
        brunnels: Dictionary of all brunnels to analyze
    """
    # Find all nearby brunnels (those with route spans, regardless of other exclusion reasons)
    nearby_brunnels = [
        b
        for b in brunnels.values()
        if b.is_representative()
        and b.route_span is not None
        and b.exclusion_reason != ExclusionReason.OUTLIER
    ]

    if not nearby_brunnels:
        print("No nearby brunnels found")
        return

    # Sort by start distance in decameters, then by end distance
    nearby_brunnels.sort(
        key=lambda b: (
            int(b.route_span.start_distance / 10) if b.route_span else 0,
            b.route_span.end_distance if b.route_span else 0.0,
        )
    )

    # Count bridges and tunnels by type and inclusion status
    bridge_count = tunnel_count = 0
    included_bridge_count = included_tunnel_count = 0

    for brunnel in nearby_brunnels:
        is_included = brunnel.exclusion_reason == ExclusionReason.NONE
        if brunnel.brunnel_type == BrunnelType.BRIDGE:
            bridge_count += 1
            if is_included:
                included_bridge_count += 1
        else:  # TUNNEL
            tunnel_count += 1
            if is_included:
                included_tunnel_count += 1

    print(
        f"Nearby brunnels ({included_bridge_count}/{bridge_count} bridges; {included_tunnel_count}/{tunnel_count} tunnels):"
    )

    # Calculate maximum digits needed for formatting alignment
    max_distance = max(
        brunnel.route_span.end_distance / 1000
        for brunnel in nearby_brunnels
        if brunnel.route_span
    )
    max_length = max(
        (brunnel.route_span.end_distance - brunnel.route_span.start_distance) / 1000
        for brunnel in nearby_brunnels
        if brunnel.route_span
    )

    # Determine width needed for distances (digits before decimal point)
    distance_width = len(f"{max_distance:.0f}") + 3  # +3 for ".XX"
    length_width = len(f"{max_length:.0f}") + 3  # +3 for ".XX"

    current_overlap_group = None

    for brunnel in nearby_brunnels:
        route_span = brunnel.route_span or RouteSpan(0, 0)
        start_km = route_span.start_distance / 1000
        end_km = route_span.end_distance / 1000
        length_km = (route_span.end_distance - route_span.start_distance) / 1000

        # Format with aligned padding
        span_info = f"{start_km:{distance_width}.2f}-{end_km:{distance_width}.2f} km ({length_km:{length_width}.2f} km)"
        annotation = "*"
        reason = ""
        if brunnel.exclusion_reason != ExclusionReason.NONE:
            annotation = "-"
            reason = f" ({brunnel.exclusion_reason.value})"
        indent = "" if brunnel.overlap_group is None else "  "
        if (
            current_overlap_group is not None or brunnel.overlap_group is not None
        ) and current_overlap_group != brunnel.overlap_group:
            current_overlap_group = brunnel.overlap_group
            if current_overlap_group is not None:
                print("--- Overlapping ---" + "-" * (len(span_info) - 20))
            else:
                print("-" * len(span_info))

        print(
            f"{span_info} {annotation} {indent}{brunnel.get_short_description()} {reason}"
        )


def exclude_uncontained_brunnels(
    route_geometry: BaseGeometry, brunnels: Dict[str, Brunnel]
) -> None:
    """
    Excludes brunnels that are not contained within the given route geometry.

    Args:
        route_geometry: The Shapely geometry of the (buffered) route.
        brunnels: A dictionary of Brunnel objects to check.

    """

    for brunnel in brunnels.values():
        if (
            brunnel.exclusion_reason == ExclusionReason.NONE
            and not brunnel.is_contained_by(route_geometry)
        ):
            brunnel.exclusion_reason = ExclusionReason.OUTLIER


def main():
    """
    Parses command-line arguments, processes the GPX file,
    finds brunnels, and generates an interactive map.
    """
    parser = create_argument_parser()
    args = parser.parse_args()

    if not args.filename:
        parser.print_help()
        sys.exit(1)

    # Setup logging
    setup_logging(args)

    # Determine output filename
    try:
        output_filename = determine_output_filename(args.filename, args.output)
        logger.debug(f"Output filename: {output_filename}")
    except (RuntimeError, ValueError):
        sys.exit(1)

    # Load and parse the GPX file into a route
    try:
        route = Route.from_file(args.filename)
    except FileNotFoundError:
        logger.error(f"GPX file not found: {args.filename}")
        sys.exit(1)
    except PermissionError:
        logger.error(f"Cannot read GPX file (permission denied): {args.filename}")
        sys.exit(1)
    except gpx.GPXException as e:
        logger.error(f"Invalid GPX file: {e}")
        sys.exit(1)
    logger.info(f"Loaded GPX route with {len(route)} points")

    logger.info(f"Total route distance: {route.linestring.length / 1000:.2f} km")

    # Find bridges and tunnels near the route
    brunnels = route.find_brunnels(args)

    logger.info(f"Found {len(brunnels)} brunnels near route")

    excluded_count = len(
        [b for b in brunnels.values() if b.exclusion_reason != ExclusionReason.NONE]
    )

    if excluded_count > 0:
        logger.debug(f"{excluded_count} brunnels excluded (will show greyed out)")

    route_geometry = route.calculate_buffered_route_geometry(args.route_buffer)

    # Check for containment within the route buffer
    exclude_uncontained_brunnels(route_geometry, brunnels)

    route.calculate_route_spans(brunnels)

    # Exclude misaligned brunnels based on bearing tolerance
    if args.bearing_tolerance > 0:
        route.exclude_misaligned_brunnels(brunnels, args.bearing_tolerance)

    # Count contained vs total brunnels
    bridges = [b for b in brunnels.values() if b.brunnel_type == BrunnelType.BRIDGE]
    tunnels = [b for b in brunnels.values() if b.brunnel_type == BrunnelType.TUNNEL]
    contained_bridges = [
        b for b in bridges if b.exclusion_reason == ExclusionReason.NONE
    ]
    contained_tunnels = [
        b for b in tunnels if b.exclusion_reason == ExclusionReason.NONE
    ]

    logger.debug(
        f"Found {len(contained_bridges)}/{len(bridges)} contained bridges and {len(contained_tunnels)}/{len(tunnels)} contained tunnels"
    )

    find_compound_brunnels(brunnels)
    if not args.no_overlap_exclusion:
        route.exclude_overlapping_brunnels(brunnels)

    # Log all nearby brunnels (included and excluded with reasons)
    log_nearby_brunnels(brunnels)

    # Collect metrics before creating map
    metrics = collect_metrics(brunnels)

    # Create visualization map
    try:
        visualization.create_route_map(route, output_filename, brunnels, metrics, args)
    except Exception as e:
        logger.error(f"Failed to create map: {e}")
        sys.exit(1)

    log_metrics(brunnels, metrics, args)

    # Automatically open the HTML file in the default browser
    if not args.no_open:
        open_file_in_browser(output_filename)


if __name__ == "__main__":
    main()
