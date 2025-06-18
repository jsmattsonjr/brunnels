#!/usr/bin/env python3
"""
Geometry and distance calculation utilities for route analysis.
"""

from typing import NamedTuple
import logging
import math

logger = logging.getLogger(__name__)


class Position(NamedTuple):
    """Represents a geographic position with latitude and longitude."""

    latitude: float
    longitude: float
