#!/usr/bin/env python3
"""
Base Brunnel class and related enums/data classes for bridge and tunnel objects.
"""

from abc import ABC, abstractmethod
from typing import Optional, List
from dataclasses import dataclass
from enum import Enum
import logging

from .geometry import Geometry
from .distance_utils import find_closest_point_on_route

logger = logging.getLogger(__name__)


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


class Brunnel(Geometry, ABC):
    """Abstract base class for bridge and tunnel objects."""

    def __init__(
        self,
        brunnel_type: BrunnelType,
        contained_in_route: bool = False,
        filter_reason: FilterReason = FilterReason.NONE,
        route_span: Optional[RouteSpan] = None,
    ):
        super().__init__()
        self.brunnel_type = brunnel_type
        self.contained_in_route = contained_in_route
        self.filter_reason = filter_reason
        self.route_span = route_span

    @abstractmethod
    def to_html(self) -> str:
        """Format brunnel metadata into HTML for popup display."""
        pass

    @abstractmethod
    def get_id(self) -> str:
        """Get a string identifier for this brunnel."""
        pass

    @abstractmethod
    def get_display_name(self) -> str:
        """Get the display name for this brunnel (e.g., 'Main Street' or 'unnamed')."""
        pass

    @abstractmethod
    def get_short_description(self) -> str:
        """Get a short description for logging (e.g., 'Bridge: Main Street (123456)')."""
        pass

    def get_log_description(self) -> str:
        """Get a standardized description for logging with route span info."""
        if self.route_span:
            span_info = f"{self.route_span.start_distance_km:.2f}-{self.route_span.end_distance_km:.2f} km (length: {self.route_span.length_km:.2f} km)"
            return f"{self.get_short_description()} {span_info}"
        else:
            return f"{self.get_short_description()} (no route span)"

    def is_contained_by(self, route_geometry) -> bool:
        """
        Check if this brunnel is completely contained within a route geometry.

        Args:
            route_geometry: Shapely geometry object representing the buffered route polygon

        Returns:
            True if the route geometry completely contains this brunnel, False otherwise
        """
        try:
            # Get cached LineString from brunnel
            brunnel_line = self.get_linestring()
            if brunnel_line is None:
                return False

            # Check if route geometry completely contains the brunnel
            return route_geometry.contains(brunnel_line)

        except Exception as e:
            logger.warning(
                f"Failed to check containment for brunnel {self.get_id()}: {e}"
            )
            return False

    def calculate_route_span(
        self, route, cumulative_distances: List[float]
    ) -> RouteSpan:
        """
        Calculate the span of this brunnel along the route.

        Args:
            route: Route object representing the route
            cumulative_distances: Pre-calculated cumulative distances along route

        Returns:
            RouteSpan object with start/end distances and length
        """
        coords = self.coordinate_list
        if not coords:
            return RouteSpan(0.0, 0.0, 0.0)

        min_distance = float("inf")
        max_distance = -float("inf")

        # Find the closest route point for each brunnel coordinate
        for brunnel_point in coords:
            cumulative_dist, _ = find_closest_point_on_route(
                brunnel_point, route.positions, cumulative_distances
            )

            min_distance = min(min_distance, cumulative_dist)
            max_distance = max(max_distance, cumulative_dist)

        return RouteSpan(min_distance, max_distance, max_distance - min_distance)

    def is_aligned_with_route(self, route, tolerance_degrees: float) -> bool:
        """
        Check if this brunnel's bearing is aligned with the route at their closest point.

        Args:
            route: Route object representing the route
            tolerance_degrees: Allowed bearing deviation in degrees

        Returns:
            True if brunnel is aligned with route within tolerance, False otherwise
        """
        from .distance_utils import (
            find_closest_segments,
            calculate_bearing,
            bearings_aligned,
        )

        coords = self.coordinate_list
        if not coords or len(coords) < 2:
            logger.debug(
                f"{self.get_short_description()} has insufficient coordinates for bearing calculation"
            )
            return False

        if not route.positions or len(route.positions) < 2:
            logger.debug("Route has insufficient coordinates for bearing calculation")
            return False

        # Find closest segments between brunnel and route
        brunnel_segment, route_segment = find_closest_segments(coords, route.positions)

        if brunnel_segment is None or route_segment is None:
            logger.debug(
                f"Could not find closest segments for {self.get_short_description()}"
            )
            return False

        # Extract segment coordinates
        _, brunnel_start, brunnel_end = brunnel_segment
        _, route_start, route_end = route_segment

        # Calculate bearings for both segments
        brunnel_bearing = calculate_bearing(brunnel_start, brunnel_end)
        route_bearing = calculate_bearing(route_start, route_end)

        # Check if bearings are aligned
        aligned = bearings_aligned(brunnel_bearing, route_bearing, tolerance_degrees)

        logger.debug(
            f"{self.get_short_description()}: brunnel_bearing={brunnel_bearing:.1f}°, route_bearing={route_bearing:.1f}°, aligned={aligned} (tolerance={tolerance_degrees}°)"
        )

        return aligned
