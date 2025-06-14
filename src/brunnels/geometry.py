#!/usr/bin/env python3
"""
Base geometry classes for brunnel analysis.
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Tuple
from dataclasses import dataclass, field
from shapely.geometry import LineString
from geopy.distance import geodesic
import math


@dataclass
class Position:
    latitude: float
    longitude: float
    elevation: Optional[float] = None

    def has_elevation(self) -> bool:
        """Check if position has elevation data."""
        return self.elevation is not None

    def distance_to(self, other: "Position") -> float:
        """
        Calculate the geodesic distance between this position and another position using geopy.

        Args:
            other: The other position

        Returns:
            Distance in kilometers
        """
        return geodesic(
            (self.latitude, self.longitude), (other.latitude, other.longitude)
        ).kilometers

    def bearing_to(self, other: "Position") -> float:
        """
        Calculate the bearing from this position to another position in degrees (0-360, where 0 is north).

        Args:
            other: Ending position

        Returns:
            Bearing in degrees (0-360, where 0° is north, 90° is east)
        """
        if self == other:
            return 0.0

        # Handle polar cases
        if math.isclose(self.latitude, 90.0):  # Start is North Pole
            return 180.0
        if math.isclose(self.latitude, -90.0):  # Start is South Pole
            return 0.0
        if math.isclose(other.latitude, 90.0):  # End is North Pole
            return 0.0
        if math.isclose(other.latitude, -90.0):  # End is South Pole
            return 180.0

        lat1 = math.radians(self.latitude)
        lat2 = math.radians(other.latitude)
        lon1 = math.radians(self.longitude)
        lon2 = math.radians(other.longitude)

        dlon = lon2 - lon1

        y = math.sin(dlon) * math.cos(lat2)
        x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(
            lat2
        ) * math.cos(dlon)

        bearing = math.atan2(y, x)
        bearing = math.degrees(bearing)
        bearing = (bearing + 360) % 360  # Normalize to 0-360

        return bearing

    def to_line_segment_distance_and_projection(
        self, seg_start: "Position", seg_end: "Position"
    ) -> Tuple[float, float, "Position"]:
        """
        Calculate the distance from a point to a line segment and find the closest point on the segment.

        Args:
            point: Point to measure distance from
            seg_start: Start of line segment
            seg_end: End of line segment

        Returns:
            Tuple of (distance_km, parameter_t, closest_point) where:
            - distance_km: Shortest distance from point to segment in km
            - parameter_t: Parameter (0-1) indicating position along segment (0=start, 1=end)
            - closest_point: Position of closest point on the segment
        """
        # Convert to radians for calculation
        lat_p, lon_p = math.radians(self.latitude), math.radians(self.longitude)
        lat_a, lon_a = math.radians(seg_start.latitude), math.radians(
            seg_start.longitude
        )
        lat_b, lon_b = math.radians(seg_end.latitude), math.radians(seg_end.longitude)

        # For small distances, we can approximate using projected coordinates
        # This is much simpler than spherical geometry and adequate for local calculations

        # Project to approximate Cartesian coordinates (meters)
        earth_radius = 6371000  # meters
        cos_lat_avg = math.cos((lat_a + lat_b) / 2)

        # Convert to meters from start point
        x_p = (lon_p - lon_a) * earth_radius * cos_lat_avg
        y_p = (lat_p - lat_a) * earth_radius

        x_a = 0.0
        y_a = 0.0

        x_b = (lon_b - lon_a) * earth_radius * cos_lat_avg
        y_b = (lat_b - lat_a) * earth_radius

        # Vector from A to B
        dx = x_b - x_a
        dy = y_b - y_a

        # Handle degenerate case where segment has zero length
        if dx == 0 and dy == 0:
            distance_m = math.sqrt(x_p**2 + y_p**2)
            return distance_m / 1000.0, 0.0, seg_start

        # Project point onto line defined by segment
        # t = ((P-A) · (B-A)) / |B-A|²
        t = ((x_p - x_a) * dx + (y_p - y_a) * dy) / (dx**2 + dy**2)

        # Clamp t to [0, 1] to stay within segment
        t = max(0.0, min(1.0, t))

        # Find closest point on segment
        x_closest = x_a + t * dx
        y_closest = y_a + t * dy

        # Calculate distance
        distance_m = math.sqrt((x_p - x_closest) ** 2 + (y_p - y_closest) ** 2)

        # Convert closest point back to lat/lon
        lat_closest = lat_a + (y_closest / earth_radius)
        lon_closest = lon_a + (x_closest / (earth_radius * cos_lat_avg))

        closest_point = Position(
            latitude=math.degrees(lat_closest), longitude=math.degrees(lon_closest)
        )

        return distance_m / 1000.0, t, closest_point


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
