#!/usr/bin/env python3
"""
Filename utilities for generating output filenames.
"""

import os
import logging

logger = logging.getLogger(__name__)


def generate_output_filename(input_filename: str) -> str:
    """
    Generates an output HTML filename and reserves it by creating an empty file.

    Strategy:
    1. If input ends with .gpx (case-insensitive), drop it
    2. Append " map.html"
    3. If file exists, try " (1).html", " (2).html", etc. (by attempting to create exclusively)
    4. Stop at 180 attempts (antimeridian reference)
    5. Use exclusive open (`open(path, 'x')`) to avoid race conditions and reserve the name.

    Args:
        input_filename: Path to the input GPX file

    Returns:
        Safe output filename that has been created as an empty file to reserve its name

    Raises:
        RuntimeError: If no available filename found after 180 attempts
        ValueError: If a filename cannot be created (e.g., due to permissions or an invalid name detected by the OS)
    """
    # Get the directory and base name
    input_dir = os.path.dirname(input_filename)
    input_base = os.path.basename(input_filename)

    # Remove .gpx extension if present (case-insensitive)
    if input_base.lower().endswith(".gpx"):
        base_name = input_base[:-4]  # Remove last 4 characters (.gpx)
    else:
        base_name = input_base

    # Construct the base output filename
    base_output = base_name + " map"

    # Try the base filename first
    candidate = os.path.join(input_dir, base_output + ".html")
    try:
        with open(candidate, "x") as f:
            pass  # File created successfully and is kept
        return candidate  # Found and reserved a good filename
    except FileExistsError:
        pass  # File already exists, proceed to numbered variants
    except (PermissionError, OSError) as e:
        logger.error(f"Cannot create file {candidate}: {e}")
        raise ValueError(f"Cannot create file: {e}")

    # Try numbered variants
    for i in range(1, 181):  # 1 to 180 (antimeridian reference)
        candidate = os.path.join(input_dir, f"{base_output} ({i}).html")
        try:
            with open(candidate, "x") as f:
                pass  # File created successfully and is kept
            return candidate  # Found and reserved a good filename
        except FileExistsError:
            continue  # File already exists, try next number
        except (PermissionError, OSError) as e:
            logger.error(f"Cannot create file {candidate}: {e}")
            raise ValueError(f"Cannot create file: {e}")

    # If we get here, we've tried 180 files and none worked
    logger.error(
        f"Could not find an available filename after 180 attempts. "
        f"Like GPX routes that cross the antimeridian, this is not supported! "
        f"Please clean up your output directory or specify --output explicitly."
    )
    raise RuntimeError("No available filename found after 180 attempts")
