#!/usr/bin/env python3
"""
Data models for brunnel analysis.
"""

from typing import Optional
from dataclasses import dataclass


@dataclass
class Position:
    latitude: float
    longitude: float
    elevation: Optional[float] = None

    def has_elevation(self) -> bool:
        """Check if position has elevation data."""
        return self.elevation is not None
