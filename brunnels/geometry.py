#!/usr/bin/env python3
"""
Base geometry classes for brunnel analysis.
"""

from abc import ABC, abstractmethod
from typing import List, Optional
from dataclasses import dataclass, field
from shapely.geometry import LineString


@dataclass
class Position:
    latitude: float
    longitude: float
    elevation: Optional[float] = None

    def has_elevation(self) -> bool:
        """Check if position has elevation data."""
        return self.elevation is not None


@dataclass
class Geometry(ABC):
    """Base class for geometric objects that can be represented as LineStrings."""

    _linestring: Optional[LineString] = field(default=None, init=False, repr=False)

    @property
    @abstractmethod
    def coordinate_list(self) -> List[Position]:
        """Return the list of Position objects for this geometry."""
        pass

    def get_linestring(self) -> Optional[LineString]:
        """
        Get memoized LineString representation of this geometry's coordinates.

        Returns:
            LineString object, or None if coordinates is empty or has less than 2 points
        """
        if self._linestring is None:
            self._linestring = self._positions_to_linestring(self.coordinate_list)
        return self._linestring

    def get_visualization_coordinates(self) -> List[List[float]]:
        """
        Get coordinates formatted for visualization (folium maps).

        Returns:
            List of [latitude, longitude] pairs
        """
        return [[pos.latitude, pos.longitude] for pos in self.coordinate_list]

    @staticmethod
    def _positions_to_linestring(positions: List[Position]) -> Optional[LineString]:
        """
        Convert a list of Position objects to a Shapely LineString.

        Args:
            positions: List of Position objects

        Returns:
            LineString object, or None if positions is empty or has less than 2 points
        """
        if not positions or len(positions) < 2:
            return None

        coords = [(pos.longitude, pos.latitude) for pos in positions]
        return LineString(coords)
