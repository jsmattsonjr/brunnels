import pytest
import math
from hypothesis import given, strategies as st, assume
from brunnels.geometry import Position
from brunnels.geometry_utils import (
    haversine_distance, 
    calculate_bearing,
    point_to_line_segment_distance_and_projection,
    calculate_cumulative_distances,
    bearings_aligned
)

# Strategy for valid GPS coordinates
valid_lat = st.floats(-85.0, 85.0)  # Exclude poles per route validation
valid_lon = st.floats(-180.0, 180.0)
valid_position = st.builds(Position, latitude=valid_lat, longitude=valid_lon)

class TestDistanceProperties:
    
    @given(valid_position, valid_position)
    def test_distance_is_non_negative(self, pos1, pos2):
        """Distance between any two points is always non-negative."""
        distance = haversine_distance(pos1, pos2)
        assert distance >= 0
    
    @given(valid_position)
    def test_distance_to_self_is_zero(self, pos):
        """Distance from a point to itself is always zero."""
        distance = haversine_distance(pos, pos)
        assert distance == 0
    
    @given(valid_position, valid_position)
    def test_distance_is_symmetric(self, pos1, pos2):
        """Distance from A to B equals distance from B to A."""
        dist_ab = haversine_distance(pos1, pos2)
        dist_ba = haversine_distance(pos2, pos1)
        assert abs(dist_ab - dist_ba) < 1e-10  # Account for floating point precision
    
    @given(valid_position, valid_position, valid_position)
    def test_triangle_inequality(self, pos1, pos2, pos3):
        """For any triangle, sum of two sides >= third side."""
        d12 = haversine_distance(pos1, pos2)
        d23 = haversine_distance(pos2, pos3)
        d13 = haversine_distance(pos1, pos3)
        
        # Triangle inequality in all permutations
        assert d12 + d23 >= d13 - 1e-10  # Small epsilon for floating point
        assert d12 + d13 >= d23 - 1e-10
        assert d23 + d13 >= d12 - 1e-10


class TestBearingProperties:
    
    @given(valid_position, valid_position)
    def test_bearing_range(self, pos1, pos2):
        """Bearing is always in range [0, 360)."""
        assume(haversine_distance(pos1, pos2) > 1e-6)  # Avoid identical points
        
        bearing = calculate_bearing(pos1, pos2)
        assert 0 <= bearing < 360
    
    @given(valid_position, valid_position)
    def test_opposite_bearing_property(self, pos1, pos2):
        """Bearing from A to B should be ~180° different from B to A."""
        assume(haversine_distance(pos1, pos2) > 1e-3)  # Avoid very close points
        
        bearing_ab = calculate_bearing(pos1, pos2)
        bearing_ba = calculate_bearing(pos2, pos1)
        
        # Calculate difference, handling wraparound
        diff = abs(bearing_ab - bearing_ba)
        diff = min(diff, 360 - diff)
        
        # Should be approximately 180° (within 1° tolerance for floating point)
        assert abs(diff - 180) < 1.0
    
    @given(st.floats(0, 360), st.floats(0, 360), st.floats(0, 90))
    def test_bearing_alignment_symmetry(self, bearing1, bearing2, tolerance):
        """Bearing alignment should be symmetric."""
        aligned_12 = bearings_aligned(bearing1, bearing2, tolerance)
        aligned_21 = bearings_aligned(bearing2, bearing1, tolerance)
        assert aligned_12 == aligned_21
    
    @given(st.floats(0, 360), st.floats(0, 45))
    def test_bearing_self_alignment(self, bearing, tolerance):
        """A bearing should always be aligned with itself."""
        assert bearings_aligned(bearing, bearing, tolerance)


class TestProjectionProperties:
    
    @given(valid_position, valid_position, valid_position)
    def test_projection_parameter_bounds(self, point, seg_start, seg_end):
        """Projection parameter t should be in [0, 1] for closest point on segment."""
        assume(haversine_distance(seg_start, seg_end) > 1e-6)  # Non-degenerate segment
        
        distance, t, closest_point = point_to_line_segment_distance_and_projection(
            point, seg_start, seg_end
        )
        
        assert 0 <= t <= 1
        assert distance >= 0
    
    @given(valid_position, valid_position)
    def test_projection_endpoints(self, seg_start, seg_end):
        """Projecting segment endpoints should give t=0 and t=1."""
        assume(haversine_distance(seg_start, seg_end) > 1e-6)
        
        # Project start point
        _, t_start, _ = point_to_line_segment_distance_and_projection(
            seg_start, seg_start, seg_end
        )
        assert abs(t_start - 0) < 1e-10
        
        # Project end point  
        _, t_end, _ = point_to_line_segment_distance_and_projection(
            seg_end, seg_start, seg_end
        )
        assert abs(t_end - 1) < 1e-10


class TestCumulativeDistanceProperties:
    
    @given(st.lists(valid_position, min_size=1, max_size=100))
    def test_cumulative_distances_monotonic(self, positions):
        """Cumulative distances should be non-decreasing."""
        cumulative = calculate_cumulative_distances(positions)
        
        assert len(cumulative) == len(positions)
        assert cumulative[0] == 0  # First distance is always 0
        
        # Each distance should be >= previous
        for i in range(1, len(cumulative)):
            assert cumulative[i] >= cumulative[i-1]
    
    @given(st.lists(valid_position, min_size=2, max_size=100))
    def test_cumulative_distances_consistency(self, positions):
        """Sum of individual segments should equal total cumulative distance."""
        cumulative = calculate_cumulative_distances(positions)
        
        # Calculate total by summing individual segments
        total_manual = 0
        for i in range(1, len(positions)):
            total_manual += haversine_distance(positions[i-1], positions[i])
        
        # Should match final cumulative distance
        assert abs(cumulative[-1] - total_manual) < 1e-10


class TestBoundingBoxProperties:
    
    @given(st.lists(valid_position, min_size=1, max_size=100), 
           st.floats(0, 10))  # Buffer in km
    def test_bbox_contains_all_points(self, positions, buffer_km):
        """Bounding box should contain all route points."""
        from brunnels.route import Route
        
        route = Route(positions)
        south, west, north, east = route.get_bbox(buffer_km)
        
        # All points should be within bbox
        for pos in positions:
            assert south <= pos.latitude <= north
            assert west <= pos.longitude <= east
    
    @given(st.lists(valid_position, min_size=1, max_size=100))
    def test_bbox_buffer_expansion(self, positions):
        """Larger buffer should never shrink bounding box."""
        from brunnels.route import Route
        
        route = Route(positions)
        
        bbox_small = route.get_bbox(0.1)  # Small buffer
        bbox_large = route.get_bbox(1.0)  # Large buffer
        
        # Large buffer bbox should contain small buffer bbox
        assert bbox_large[0] <= bbox_small[0]  # south
        assert bbox_large[1] <= bbox_small[1]  # west  
        assert bbox_large[2] >= bbox_small[2]  # north
        assert bbox_large[3] >= bbox_small[3]  # east


class TestCoordinateCombinerProperties:
    
    @given(st.lists(st.lists(valid_position, min_size=2, max_size=10), 
                   min_size=2, max_size=5))
    def test_coordinate_combining_preserves_total_length(self, component_coords):
        """Combined coordinates should preserve total geometric length."""
        from brunnels.brunnel_way import BrunnelWay
        from brunnels.coordinate_combiner import combine_osm_way_coordinates
        from brunnels.brunnel import BrunnelType
        
        # Create mock BrunnelWay components
        components = []
        total_individual_length = 0
        
        for i, coords in enumerate(component_coords):
            # Create fake metadata with nodes (needed for adjacency detection)
            metadata = {
                'id': i,
                'nodes': list(range(i*100, i*100 + len(coords))),
                'tags': {'bridge': 'yes'}
            }
            
            component = BrunnelWay(coords, metadata, BrunnelType.BRIDGE)
            components.append(component)
            
            # Calculate length of this component
            for j in range(1, len(coords)):
                total_individual_length += haversine_distance(coords[j-1], coords[j])
        
        try:
            combined_coords = combine_osm_way_coordinates(components)
            
            # Calculate combined length
            combined_length = 0
            for i in range(1, len(combined_coords)):
                combined_length += haversine_distance(combined_coords[i-1], combined_coords[i])
            
            # Should be approximately equal (within 1% tolerance for coordinate precision)
            assert abs(combined_length - total_individual_length) / max(total_individual_length, 1e-6) < 0.01
            
        except ValueError:
            # If combining fails due to non-adjacency, that's acceptable
            pass


# Run with: pytest -v --hypothesis-show-statistics
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--hypothesis-show-statistics"])