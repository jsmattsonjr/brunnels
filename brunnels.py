#!/usr/bin/env python3
"""
Brunnel (Bridge/Tunnel) Visualization Tool


Requirements:
    pip install gpxpy folium requests shapely

"""


import subprocess
import argparse
import platform
import logging
import sys
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
        help="Route buffer for intersection detection in meters (default: 3.0)",
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

    args = parser.parse_args()

    # Setup logging
    setup_logging(args.log_level)

    try:
        # Load and parse the GPX file into a route
        route = gpx.load_gpx_route(args.filename)
        logger.info(f"Loaded GPX route with {len(route)} points")

        # Find bridges and tunnels near the route (intersection detection included)
        brunnels = overpass.find_route_brunnels(route, args.buffer, args.route_buffer)

        # Count intersecting vs total brunnels
        bridges = [b for b in brunnels if b.brunnel_type == BrunnelType.BRIDGE]
        tunnels = [b for b in brunnels if b.brunnel_type == BrunnelType.TUNNEL]
        intersecting_bridges = [b for b in bridges if b.intersects_route]
        intersecting_tunnels = [b for b in tunnels if b.intersects_route]

        logger.info(
            f"Found {len(intersecting_bridges)}/{len(bridges)} intersecting bridges and {len(intersecting_tunnels)}/{len(tunnels)} intersecting tunnels"
        )

        # TODO: Process the route for brunnel analysis (intersection detection)

        # Create visualization map
        visualization.create_route_map(route, args.output, brunnels)
        logger.info(f"Map saved to {args.output}")

        # Automatically open the HTML file in the default browser
        if not args.no_open:
            try:
                system = platform.system()
                if system == "Darwin":  # macOS
                    subprocess.run(["open", args.output])
                    logger.info(f"Opening {args.output} in your default browser...")
                elif system == "Windows":
                    subprocess.run(["start", args.output], shell=True)
                    logger.info(f"Opening {args.output} in your default browser...")
                elif system == "Linux":
                    subprocess.run(["xdg-open", args.output])
                    logger.info(f"Opening {args.output} in your default browser...")
                else:
                    logger.info(
                        f"Please open {args.output} manually in your web browser"
                    )
            except Exception as e:
                logger.warning(f"Could not automatically open browser: {e}")
                logger.info(f"Please manually run: open {args.output}")

    except (FileNotFoundError, PermissionError) as e:
        logger.error(f"Failed to read file '{args.filename}': {e}")
        sys.exit(1)
    except gpxpy.gpx.GPXException as e:
        logger.error(f"Failed to parse GPX file: {e}")
        sys.exit(1)
    except gpx.RouteValidationError as e:
        logger.error(f"Route validation failed: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
