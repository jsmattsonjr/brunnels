#!/usr/bin/env python3
"""
Data models for brunnel analysis.
"""

from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from enum import Enum
from geometry import Position, Geometry


class BrunnelType(Enum):
    """Enumeration for brunnel (bridge/tunnel) types."""

    BRIDGE = "bridge"
    TUNNEL = "tunnel"

    def __str__(self) -> str:
        return self.value.capitalize()


class FilterReason(Enum):
    """Enumeration for brunnel filtering reasons."""

    NONE = "none"
    BICYCLE_NO = "bicycle=no"
    WATERWAY = "has waterway tag"
    RAILWAY = "railway (not abandoned)"
    POLYGON = "closed way (first node equals last node)"
    NOT_CONTAINED = "not contained within route buffer"
    NO_ROUTE_SPAN = "failed to calculate route span"
    UNALIGNED = "bearing not aligned with route"
    NOT_NEAREST = "not nearest among overlapping brunnels"
    MERGED = "merged into adjacent brunnel"

    def __str__(self) -> str:
        return self.value


class Direction(Enum):
    """Enumeration for brunnel direction relative to route."""

    FORWARD = "forward"
    REVERSE = "reverse"

    def __str__(self) -> str:
        return self.value


@dataclass
class RouteSpan:
    """Information about where a brunnel spans along a route."""

    start_distance_km: float  # Distance from route start where brunnel begins
    end_distance_km: float  # Distance from route start where brunnel ends
    length_km: float  # Length of route spanned by brunnel

    def __post_init__(self):
        """Calculate length after initialization."""
        self.length_km = self.end_distance_km - self.start_distance_km


@dataclass
class BrunnelWay(Geometry):
    coords: List[Position]
    metadata: Dict[str, Any]
    brunnel_type: BrunnelType
    contained_in_route: bool = False
    filter_reason: FilterReason = FilterReason.NONE
    route_span: Optional[RouteSpan] = None

    @property
    def coordinate_list(self) -> List[Position]:
        """Return the list of Position objects for this geometry."""
        return self.coords
