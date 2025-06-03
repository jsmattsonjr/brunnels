#!/usr/bin/env python3
"""
Filename utilities for generating output filenames.
"""

import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def generate_output_filename(input_filename: str) -> str:
    """
    Generate an output HTML filename based on the input filename.

    Strategy:
    1. If input ends with .gpx (case-insensitive), drop it
    2. Append " map.html"
    3. If file exists, try " (1).html", " (2).html", etc.
    4. Stop at 180 attempts (antimeridian reference)
    5. Use exclusive open to avoid race conditions

    Args:
        input_filename: Path to the input GPX file

    Returns:
        Safe output filename that doesn't exist yet

    Raises:
        RuntimeError: If no available filename found after 180 attempts
        ValueError: If constructed filename would be illegal
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

    # Validate the base filename before proceeding
    _validate_filename_component(base_output)

    # Try the base filename first
    candidate = os.path.join(input_dir, base_output + ".html")
    _validate_full_path(candidate)

    if _try_create_file(candidate):
        return candidate

    # Try numbered variants
    for i in range(1, 181):  # 1 to 180 (antimeridian reference)
        candidate = os.path.join(input_dir, f"{base_output} ({i}).html")
        _validate_full_path(candidate)

        if _try_create_file(candidate):
            return candidate

    # If we get here, we've tried 180 files and none worked
    logger.error(
        f"Could not find an available filename after 180 attempts. "
        f"Like GPX routes that cross the antimeridian, this is not supported! "
        f"Please clean up your output directory or specify --output explicitly."
    )
    raise RuntimeError("No available filename found after 180 attempts")


def _validate_filename_component(filename: str) -> None:
    """
    Validate that a filename component is legal.

    We assume the input filename is valid and we only add safe characters.
    This is a simple sanity check for our constructed filename.

    Args:
        filename: Filename component to validate (without directory or extension)

    Raises:
        ValueError: If filename has obvious issues
    """
    # Check for empty filename
    if not filename or filename.isspace():
        logger.error("Filename is empty or contains only whitespace")
        raise ValueError("Filename cannot be empty")


def _validate_full_path(filepath: str) -> None:
    """
    Validate that a full file path is reasonable.

    Args:
        filepath: Full file path to validate

    Raises:
        ValueError: If path is problematic
    """
    # Validate the filename component
    filename = os.path.basename(filepath)
    name_without_ext = os.path.splitext(filename)[0]
    _validate_filename_component(name_without_ext)


def _try_create_file(filepath: str) -> bool:
    """
    Try to create a file exclusively (to test if it exists and avoid race conditions).

    Args:
        filepath: Path to the file to test

    Returns:
        True if file was successfully created (and then removed), False if it already exists
    """
    try:
        # Try to create the file exclusively
        with open(filepath, "x") as f:
            pass  # File created successfully

        # Remove the file immediately since we were just testing
        os.remove(filepath)
        return True

    except FileExistsError:
        # File already exists
        return False
    except (PermissionError, OSError) as e:
        # Some other error occurred (permissions, disk full, etc.)
        logger.error(f"Cannot create file {filepath}: {e}")
        raise ValueError(f"Cannot create file: {e}")
