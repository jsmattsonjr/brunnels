#!/usr/bin/env python3
"""
Tests for route distance conversion functionality.
"""

import pytest
from brunnels.geometry import Position
from brunnels.route import Route


class TestDistanceConversion:
    """Test distance conversion from Euclidean to Haversine."""

    def test_simple_route_distance_conversion(self):
        """Test distance conversion with a simple 3-point route."""
        coords = [
            Position(latitude=47.12322, longitude=-122.85051, elevation=30.84),
            Position(latitude=47.12308, longitude=-122.85048, elevation=30.96),
            Position(latitude=47.12299, longitude=-122.85039, elevation=31.15),
        ]

        route = Route(coords)

        # Test edge cases
        assert route.euclidean_to_haversine_distance(0.0) == 0.0

        # Test full route distance
        euclidean_distance = route.linestring.length
        haversine_distance = route.euclidean_to_haversine_distance(
            euclidean_distance
        )

        # The distances should be similar but not identical
        assert abs(haversine_distance - euclidean_distance) < 1.0  # Within 1 meter

        # Test intermediate distance
        mid_distance = euclidean_distance / 2
        mid_haversine = route.euclidean_to_haversine_distance(mid_distance)

        # Should be approximately half the total distance
        assert abs(mid_haversine - haversine_distance / 2) < 1.0

    def test_route_without_elevation(self):
        """Test distance conversion with a route that has no elevation data."""
        coords = [
            Position(latitude=47.12322, longitude=-122.85051, elevation=None),
            Position(latitude=47.12308, longitude=-122.85048, elevation=None),
            Position(latitude=47.12299, longitude=-122.85039, elevation=None),
        ]

        route = Route(coords)

        # Test conversion still works
        euclidean_distance = route.linestring.length
        haversine_distance = route.euclidean_to_haversine_distance(
            euclidean_distance
        )

        # Should still provide meaningful results
        assert haversine_distance > 0
        assert abs(haversine_distance - euclidean_distance) < 2.0

    def test_distance_beyond_route_length(self):
        """Test distance conversion beyond the route length."""
        coords = [
            Position(latitude=47.12322, longitude=-122.85051, elevation=30.84),
            Position(latitude=47.12308, longitude=-122.85048, elevation=30.96),
        ]

        route = Route(coords)

        euclidean_distance = route.linestring.length
        haversine_distance = route.euclidean_to_haversine_distance(
            euclidean_distance
        )

        # Test distance beyond route length
        beyond_distance = euclidean_distance * 2
        beyond_haversine = route.euclidean_to_haversine_distance(beyond_distance)

        # Should return the maximum distance
        assert beyond_haversine == haversine_distance

    def test_real_gpx_file_distance_conversion(self):
        """Test distance conversion with a real GPX file."""
        try:
            route = Route.from_file("tests/fixtures/Chehalis.gpx")

            euclidean_distance = route.linestring.length
            haversine_distance = route.euclidean_to_haversine_distance(
                euclidean_distance
            )

            # The difference should be small but measurable
            difference = abs(haversine_distance - euclidean_distance)
            percentage_diff = (difference / euclidean_distance) * 100

            # Should be within reasonable bounds (less than 1% difference)
            assert percentage_diff < 1.0

            # Should have some measurable difference for a real route
            assert difference > 0.1  # At least 10cm difference

        except FileNotFoundError:
            pytest.skip("GPX test file not found")
