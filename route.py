#!/usr/bin/env python3
"""
Route data model for brunnel analysis.
"""

from typing import Optional, Tuple, List
from dataclasses import dataclass, field
from geometry import Position, Geometry


@dataclass
class Route(Geometry):
    """Represents a GPX route with memoized geometric operations."""

    positions: List[Position]
    _bbox: Optional[Tuple[float, float, float, float]] = field(
        default=None, init=False, repr=False
    )
    _bbox_buffer_km: Optional[float] = field(default=None, init=False, repr=False)
    _cumulative_distances: Optional[List[float]] = field(
        default=None, init=False, repr=False
    )

    @property
    def coordinate_list(self) -> List[Position]:
        """Return the list of Position objects for this geometry."""
        return self.positions

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

    def get_cumulative_distances(self) -> List[float]:
        """
        Get memoized cumulative distances along the route.

        Returns:
            List of cumulative distances in kilometers, with same length as positions
        """
        if self._cumulative_distances is None:
            # Import here to avoid circular imports
            from distance_utils import calculate_cumulative_distances

            self._cumulative_distances = calculate_cumulative_distances(self.positions)

        return self._cumulative_distances

    def __len__(self) -> int:
        """Return number of positions in route."""
        return len(self.positions)

    def __getitem__(self, index):
        """Allow indexing into positions."""
        return self.positions[index]

    def __iter__(self):
        """Allow iteration over positions."""
        return iter(self.positions)
