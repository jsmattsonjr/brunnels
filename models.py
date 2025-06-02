#!/usr/bin/env python3
"""
Data models for brunnel analysis.
"""

from typing import Optional, Tuple, List, Dict, Any
from dataclasses import dataclass, field
from shapely.geometry import LineString
from enum import Enum


@dataclass
class Position:
    latitude: float
    longitude: float
    elevation: Optional[float] = None

    def has_elevation(self) -> bool:
        """Check if position has elevation data."""
        return self.elevation is not None


@dataclass
class Route:
    """Represents a GPX route with memoized geometric operations."""

    positions: List[Position]
    _linestring: Optional[LineString] = field(default=None, init=False, repr=False)
    _bbox: Optional[Tuple[float, float, float, float]] = field(
        default=None, init=False, repr=False
    )
    _bbox_buffer_km: Optional[float] = field(default=None, init=False, repr=False)

    def get_bbox(self, buffer_km: float = 1.0) -> Tuple[float, float, float, float]:
        """
        Get memoized bounding box for this route with buffer.

        Args:
            buffer_km: Buffer distance in kilometers (default: 1.0)

        Returns:
            Tuple of (south, west, north, east) in decimal degrees

        Raises:
            ValueError: If route is empty
        """
        if not self.positions:
            raise ValueError("Cannot calculate bounding box for empty route")

        if self._bbox is None or self._bbox_buffer_km != buffer_km:
            # Import here to avoid circular imports
            from gpx import _calculate_route_bbox

            self._bbox = _calculate_route_bbox(self, buffer_km)
            self._bbox_buffer_km = buffer_km

        return self._bbox

    def __len__(self) -> int:
        """Return number of positions in route."""
        return len(self.positions)

    def __getitem__(self, index):
        """Allow indexing into positions."""
        return self.positions[index]

    def __iter__(self):
        """Allow iteration over positions."""
        return iter(self.positions)

    def get_linestring(self) -> Optional[LineString]:
        """
        Get memoized LineString representation of this route's positions.

        Returns:
            LineString object, or None if positions is empty or has less than 2 points
        """
        if self._linestring is None:
            # Import here to avoid circular imports
            from geometry import positions_to_linestring

            self._linestring = positions_to_linestring(self.positions)
        return self._linestring


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
class BrunnelWay:
    coords: List[Position]
    metadata: Dict[str, Any]
    brunnel_type: BrunnelType
    contained_in_route: bool = False
    filter_reason: FilterReason = FilterReason.NONE
    route_span: Optional[RouteSpan] = None
    _linestring: Optional[LineString] = field(default=None, init=False, repr=False)

    def get_linestring(self) -> Optional[LineString]:
        """
        Get memoized LineString representation of this brunnel's coordinates.

        Returns:
            LineString object, or None if coords is empty or has less than 2 points
        """
        if self._linestring is None:
            # Import here to avoid circular imports
            from geometry import positions_to_linestring

            self._linestring = positions_to_linestring(self.coords)
        return self._linestring
