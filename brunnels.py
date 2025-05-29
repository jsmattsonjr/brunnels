#!/usr/bin/env python3
"""
Brunnel (Bridge/Tunnel) Visualization Tool


Requirements:
    pip install gpxpy

"""


from typing import Optional, List
from dataclasses import dataclass
import argparse
import logging
import sys
import gpxpy
import gpxpy.gpx

import gpx

# Configure logging
logger = logging.getLogger(__name__)


@dataclass
class Position:
    latitude: float
    longitude: float
    elevation: Optional[float] = None

    def has_elevation(self) -> bool:
        """Check if position has elevation data."""
        return self.elevation is not None


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
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Set logging level (default: INFO)",
    )

    args = parser.parse_args()

    # Setup logging
    setup_logging(args.log_level)

    try:
        # Load and parse the GPX file into a route
        route = gpx.load_gpx_route(args.filename)
        logger.info(f"Successfully loaded route with {len(route)} points")

        # TODO: Process the route for brunnel analysis

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
