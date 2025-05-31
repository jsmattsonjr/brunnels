#!/usr/bin/env python3
"""
Data models for brunnel analysis.
"""

from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from enum import Enum


@dataclass
class Position:
    latitude: float
    longitude: float
    elevation: Optional[float] = None

    def has_elevation(self) -> bool:
        """Check if position has elevation data."""
        return self.elevation is not None


class BrunnelType(Enum):
    """Enumeration for brunnel (bridge/tunnel) types."""

    BRIDGE = "bridge"
    TUNNEL = "tunnel"

    def __str__(self) -> str:
        return self.value.capitalize()


@dataclass
class BrunnelWay:
    coords: List[Position]
    metadata: Dict[str, Any]
    brunnel_type: BrunnelType
    intersects_route: bool = False
