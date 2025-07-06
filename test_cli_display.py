#!/usr/bin/env python3
"""
Test CLI functionality for route distance display.
"""

import sys
sys.path.insert(0, 'src')

from brunnels.route import Route
from brunnels.brunnel import Brunnel, BrunnelType, RouteSpan
from brunnels.cli import log_nearby_brunnels
from brunnels.geometry import Position


def test_cli_distance_display():
    """Test the CLI distance display functionality."""
    
    # Create a simple route
    coords = [
        Position(latitude=47.12322, longitude=-122.85051, elevation=30.84),
        Position(latitude=47.12308, longitude=-122.85048, elevation=30.96),
        Position(latitude=47.12299, longitude=-122.85039, elevation=31.15)
    ]
    
    route = Route(coords)
    
    # Create a mock brunnel with a route span
    brunnel_coords = [
        Position(latitude=47.12315, longitude=-122.85050, elevation=30.9),
        Position(latitude=47.12305, longitude=-122.85045, elevation=31.0)
    ]
    
    brunnel = Brunnel(
        coords=brunnel_coords,
        metadata={"id": "test123", "tags": {"name": "Test Bridge"}},
        brunnel_type=BrunnelType.BRIDGE,
        projection=route.projection
    )
    
    # Set a route span (normally calculated by the route analysis)
    brunnel.route_span = RouteSpan(start_distance=5.0, end_distance=15.0)
    
    brunnels = {"test123": brunnel}
    
    print("Testing CLI distance display:")
    print("=" * 50)
    
    # Test the log function
    log_nearby_brunnels(route, brunnels)
    
    print("\nDistance conversion test:")
    print(f"Euclidean start: {brunnel.route_span.start_distance:.2f}m")
    print(f"Euclidean end: {brunnel.route_span.end_distance:.2f}m")
    print(f"3D Haversine start: {route.euclidean_to_3d_haversine_distance(brunnel.route_span.start_distance):.2f}m")
    print(f"3D Haversine end: {route.euclidean_to_3d_haversine_distance(brunnel.route_span.end_distance):.2f}m")


if __name__ == "__main__":
    test_cli_distance_display()