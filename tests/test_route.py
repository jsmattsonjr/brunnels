import pytest
import os
from io import StringIO
import tempfile  # Add this to the imports at the top of the file
import math
import logging  # Added for logger mocking
from unittest.mock import patch, MagicMock  # Added for mocking
import collections  # Added for Counter, though not directly used in assertions here

from brunnels.route import Route, RouteValidationError, route_spans_overlap
from brunnels.geometry import Position  # Corrected import for RouteSpan
from brunnels.brunnel import (
    RouteSpan,
    FilterReason,
)  # RouteSpan imported from brunnel module, FilterReason added
from brunnels.brunnel_way import BrunnelWay  # Added for potential mock object creation
from gpxpy.gpx import GPXException  # Corrected import for GPXException
from brunnels.geometry_utils import haversine_distance  # Required for manual check


# Helper function to create GPX content
def gpx_content(points_data):
    """
    Generates GPX XML content string.
    points_data is a list of lists of tuples:
    [[ (lat1, lon1, ele1), (lat2, lon2, ele2), ... ],  # Track 1, Segment 1
     [ (lat3, lon3, ele3), ... ],                     # Track 1, Segment 2
     ...
    ]
    Or for multiple tracks:
    [
        [[ (lat1, lon1, ele1), ... ]], # Track 1
        [[ (lat2, lon2, ele2), ... ]]  # Track 2
    ]
    """
    gpx_start = """<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="pytest" xmlns="http://www.topografix.com/GPX/1/1" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://www.topografix.com/GPX/1/1 http://www.topografix.com/GPX/1/1/gpx.xsd">
"""
    gpx_end = "</gpx>"
    tracks_xml = ""

    # Determine if we have multiple tracks or multiple segments in one track
    if not points_data:  # Empty GPX
        pass
    elif not isinstance(
        points_data[0][0], list
    ):  # Single track, multiple segments implicitly
        points_data = [points_data]  # Wrap into a single track structure

    for track_segments_data in points_data:
        segments_xml = ""
        for segment_points in track_segments_data:
            points_xml = ""
            for lat, lon, ele in segment_points:
                if ele is not None:
                    points_xml += (
                        f'<trkpt lat="{lat}" lon="{lon}"><ele>{ele}</ele></trkpt>\n'
                    )
                else:
                    points_xml += f'<trkpt lat="{lat}" lon="{lon}"></trkpt>\n'
            segments_xml += f"<trkseg>\n{points_xml}</trkseg>\n"
        tracks_xml += f"<trk>\n{segments_xml}</trk>\n"

    return gpx_start + tracks_xml + gpx_end


# Tests for Route.from_gpx


def test_from_gpx_valid_single_track_single_segment():
    gpx_str = gpx_content([[(40.7128, -74.0060, 10.0), (40.7580, -73.9855, 12.0)]])
    route = Route.from_gpx(StringIO(gpx_str))
    assert len(route.positions) == 2
    assert route.positions[0] == Position(40.7128, -74.0060, 10.0)
    assert route.positions[1] == Position(40.7580, -73.9855, 12.0)


def test_from_gpx_valid_single_track_multi_segment():
    gpx_str = gpx_content(
        [
            [(40.7128, -74.0060, 10.0)],
            [(40.7580, -73.9855, 12.0), (40.7589, -73.9845, 13.0)],
        ]
    )
    route = Route.from_gpx(StringIO(gpx_str))
    assert len(route.positions) == 3
    assert route.positions[0] == Position(40.7128, -74.0060, 10.0)
    assert route.positions[1] == Position(40.7580, -73.9855, 12.0)
    assert route.positions[2] == Position(40.7589, -73.9845, 13.0)


def test_from_gpx_valid_multi_track():
    gpx_str = gpx_content(
        [
            [[(40.7128, -74.0060, 10.0)]],  # Track 1, Segment 1
            [
                [(40.7580, -73.9855, 12.0)],
                [(40.7589, -73.9845, 13.0)],
            ],  # Track 2, Segment 1 & 2
        ]
    )
    route = Route.from_gpx(StringIO(gpx_str))
    assert len(route.positions) == 3
    assert route.positions[0] == Position(40.7128, -74.0060, 10.0)
    assert route.positions[1] == Position(40.7580, -73.9855, 12.0)
    assert route.positions[2] == Position(40.7589, -73.9845, 13.0)


def test_from_gpx_point_without_elevation():
    gpx_str = gpx_content([[(40.7128, -74.0060, None), (40.7580, -73.9855, 12.0)]])
    route = Route.from_gpx(StringIO(gpx_str))
    assert len(route.positions) == 2
    assert route.positions[0] == Position(40.7128, -74.0060, None)
    assert route.positions[1] == Position(40.7580, -73.9855, 12.0)


def test_from_gpx_empty_no_tracks():
    # GPX file with no tracks
    gpx_str = gpx_content([])  # Pass empty list to helper
    route = Route.from_gpx(StringIO(gpx_str))
    assert len(route.positions) == 0


def test_from_gpx_empty_track_no_segments():
    # GPX file with a track but no segments
    gpx_start = """<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="pytest" xmlns="http://www.topografix.com/GPX/1/1" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://www.topografix.com/GPX/1/1 http://www.topografix.com/GPX/1/1/gpx.xsd">
<trk></trk>
</gpx>"""
    route = Route.from_gpx(StringIO(gpx_start))
    assert len(route.positions) == 0


def test_from_gpx_empty_segment_no_points():
    # GPX file with a track and a segment but no points
    gpx_str = gpx_content([[[]]])  # Track 1, Segment 1, no points
    # The helper function might create <trkseg></trkseg> which is fine
    # or it might omit it if points_xml is empty.
    # Let's construct manually for clarity if helper isn't perfect for this exact case
    gpx_manual_str = """<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="pytest" xmlns="http://www.topografix.com/GPX/1/1" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://www.topografix.com/GPX/1/1 http://www.topografix.com/GPX/1/1/gpx.xsd">
<trk><trkseg></trkseg></trk>
</gpx>"""
    route = Route.from_gpx(StringIO(gpx_manual_str))
    assert len(route.positions) == 0
    # Also test with helper if it produces valid empty segment
    route_helper = Route.from_gpx(StringIO(gpx_content([[[]]])))
    assert len(route_helper.positions) == 0


def test_from_gpx_malformed_gpx():
    gpx_str = "<gpx><trk><trkseg><trkpt lat='40.7' lon='-74.0'>"  # Missing closing tags
    with pytest.raises(GPXException):
        Route.from_gpx(StringIO(gpx_str))


def test_from_gpx_invalid_xml():
    gpx_str = "This is not XML"
    with pytest.raises(
        GPXException
    ):  # gpxpy should raise GPXException for parsing errors
        Route.from_gpx(StringIO(gpx_str))


# Tests for Route.from_file
def test_from_file_valid_gpx():
    gpx_str = gpx_content([[(40.7128, -74.0060, 10.0), (40.7580, -73.9855, 12.0)]])
    # Create a temporary file to write the GPX data
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".gpx") as tmp_file:
        tmp_file.write(gpx_str)
        tmp_file_name = tmp_file.name

    try:
        route = Route.from_file(tmp_file_name)
        assert len(route.positions) == 2
        assert route.positions[0] == Position(40.7128, -74.0060, 10.0)
        assert route.positions[1] == Position(40.7580, -73.9855, 12.0)
    finally:
        os.remove(tmp_file_name)  # Clean up the temporary file


def test_from_file_not_found():
    with pytest.raises(FileNotFoundError):
        Route.from_file("non_existent_file.gpx")


# test_from_file_permission_error - SKIPPING as it's hard to set up reliably


# Tests for Route Validation (via from_gpx)


def test_validate_route_antimeridian_crossing():
    # Longitude jumps from +170 to -170 ( > 180 degree jump)
    gpx_str = gpx_content([[(0, 170.0, 0), (0, -170.0, 0)]])
    with pytest.raises(RouteValidationError) as excinfo:
        Route.from_gpx(StringIO(gpx_str))
    assert "antimeridian" in str(excinfo.value).lower()


def test_validate_route_near_north_pole():
    # Latitude > 85.0
    gpx_str = gpx_content([[(85.1, 0, 0)]])
    with pytest.raises(RouteValidationError) as excinfo:
        Route.from_gpx(StringIO(gpx_str))
    assert (
        "pole" in str(excinfo.value).lower() or "latitude" in str(excinfo.value).lower()
    )


def test_validate_route_near_south_pole():
    # Latitude < -85.0
    gpx_str = gpx_content([[(-85.1, 0, 0)]])
    with pytest.raises(RouteValidationError) as excinfo:
        Route.from_gpx(StringIO(gpx_str))
    assert (
        "pole" in str(excinfo.value).lower() or "latitude" in str(excinfo.value).lower()
    )


def test_validate_route_valid_no_error():
    # A route that is geographically valid
    gpx_str = gpx_content([[(0, 0, 0), (10, 10, 0), (-10, -10, 0)]])
    try:
        Route.from_gpx(StringIO(gpx_str))
    except RouteValidationError:
        pytest.fail("RouteValidationError raised unexpectedly for a valid route.")


def test_validate_route_empty_route_no_error():
    # An empty route should not cause validation errors itself
    # (from_gpx handles empty points list, _validate_route might not even be called or called with empty list)
    gpx_str = gpx_content([])
    try:
        route = Route.from_gpx(StringIO(gpx_str))
        assert len(route.positions) == 0  # Route class handles empty positions list
    except RouteValidationError:
        pytest.fail("RouteValidationError raised unexpectedly for an empty route.")


# Tests for Route.get_bbox


def test_get_bbox_empty_route():
    route = Route(positions=[])
    with pytest.raises(ValueError) as excinfo:
        route.get_bbox()
    assert "empty route" in str(excinfo.value).lower()


def test_get_bbox_single_point_route_default_buffer():
    # For a single point, buffer calculation is key.
    # 1 deg lat ~ 111000 m. Buffer is 10 m by default.
    # So lat_buffer is 10/111000.0
    # lon_buffer depends on latitude. At lat 0, it's also 10/111000.0
    pos = Position(latitude=0, longitude=0, elevation=0)
    route = Route(positions=[pos])

    # Expected buffer values
    buffer = 10.0
    lat_buffer_deg = buffer / 111000.0
    lon_buffer_deg = buffer / (111000.0)  # cos(radians(0)) = 1

    expected_bbox = (
        max(-90.0, pos.latitude - lat_buffer_deg),
        max(-180.0, pos.longitude - lon_buffer_deg),
        min(90.0, pos.latitude + lat_buffer_deg),
        min(180.0, pos.longitude + lon_buffer_deg),
    )

    bbox = route.get_bbox()  # Default buffer = 1.0
    assert bbox == pytest.approx(expected_bbox)


def test_get_bbox_single_point_route_custom_buffer():
    pos = Position(latitude=45, longitude=45, elevation=0)  # Use a non-zero latitude
    route = Route(positions=[pos])

    buffer = 5.0
    lat_buffer_deg = buffer / 111000.0
    # cos(radians(45)) is math.cos(math.radians(45))
    lon_buffer_deg = buffer / (111000.0 * abs(math.cos(math.radians(pos.latitude))))

    expected_bbox = (
        max(-90.0, pos.latitude - lat_buffer_deg),
        max(-180.0, pos.longitude - lon_buffer_deg),
        min(90.0, pos.latitude + lat_buffer_deg),
        min(180.0, pos.longitude + lon_buffer_deg),
    )

    bbox = route.get_bbox(buffer=buffer)
    assert bbox == pytest.approx(expected_bbox)


def test_get_bbox_multi_point_route_no_buffer_implicitly_zero():
    # Note: get_bbox always applies a buffer. To test without, we'd need to check _calculate_bbox
    # or provide a very small buffer if the API expects it.
    # The _calculate_bbox method is what takes buffer. get_bbox uses it.
    # Let's test with default buffer first.
    positions = [
        Position(latitude=0, longitude=0, elevation=0),
        Position(latitude=1, longitude=1, elevation=0),
    ]
    route = Route(positions=positions)

    # With default buffer = 10.0
    buffer = 10.0
    avg_lat = 0.5  # (0+1)/2
    lat_buffer_deg = buffer / 111000.0
    lon_buffer_deg = buffer / (111000.0 * abs(math.cos(math.radians(avg_lat))))

    expected_bbox = (
        max(-90.0, 0.0 - lat_buffer_deg),  # min_lat - lat_buffer
        max(-180.0, 0.0 - lon_buffer_deg),  # min_lon - lon_buffer
        min(90.0, 1.0 + lat_buffer_deg),  # max_lat + lat_buffer
        min(180.0, 1.0 + lon_buffer_deg),  # max_lon + lon_buffer
    )
    bbox = route.get_bbox()  # Default buffer
    assert bbox == pytest.approx(expected_bbox)


def test_get_bbox_multi_point_route_larger_buffer():
    positions = [
        Position(latitude=10, longitude=10, elevation=0),
        Position(
            latitude=12, longitude=13, elevation=0
        ),  # min_lat=10, max_lat=12, min_lon=10, max_lon=13
    ]
    route = Route(positions=positions)

    buffer = 100.0  # Larger buffer
    avg_lat = 11.0  # (10+12)/2
    lat_buffer_deg = buffer / 111000.0
    lon_buffer_deg = buffer / (111000.0 * abs(math.cos(math.radians(avg_lat))))

    expected_bbox = (
        max(-90.0, 10.0 - lat_buffer_deg),
        max(-180.0, 10.0 - lon_buffer_deg),
        min(90.0, 12.0 + lat_buffer_deg),
        min(180.0, 13.0 + lon_buffer_deg),
    )
    bbox = route.get_bbox(buffer=buffer)
    assert bbox == pytest.approx(expected_bbox)


def test_get_bbox_memoization():
    positions = [Position(0, 0, 0), Position(1, 1, 0)]
    route = Route(positions=positions)
    bbox1 = route.get_bbox(buffer=1.0)
    # Access internal attributes for testing memoization (with caution)
    assert route._bbox is not None
    assert route._bbox_buffer == 1.0

    bbox2 = route.get_bbox(buffer=1.0)  # Same buffer, should be memoized
    assert bbox1 is bbox2  # Should be the exact same object

    bbox3 = route.get_bbox(buffer=2.0)  # Different buffer, should recompute
    assert bbox3 is not bbox1  # Should be a new object
    assert route._bbox_buffer == 2.0

    # Test that after recomputation, asking for the original buffer again recomputes (or retrieves if we cached multiple)
    # Current implementation only caches the last one.
    bbox4 = route.get_bbox(buffer=1.0)
    assert bbox4 is not bbox3
    # Depending on implementation, bbox4 might be == bbox1 if it recomputes to the same values,
    # but the key is that _calculate_bbox was called again.
    # The current implementation will recompute if buffer changes from the stored _bbox_buffer
    # So bbox4 will be a new tuple object, but its values will be same as bbox1.
    assert bbox4 == bbox1
    assert bbox4 is not bbox1  # It recomputes because _bbox_buffer was 2.0
    assert route._bbox_buffer == 1.0


# Tests for Route.get_cumulative_distances


def test_get_cumulative_distances_empty_route():
    route = Route(positions=[])
    assert route.get_cumulative_distances() == []


def test_get_cumulative_distances_single_point():
    route = Route(positions=[Position(0, 0, 0)])
    assert route.get_cumulative_distances() == [0.0]


def test_get_cumulative_distances_multi_points():
    # Points carefully chosen for easier distance checking if needed,
    # but we mostly rely on haversine_distance being correct.
    # For simplicity, let's use points where some distances are zero.
    positions = [
        Position(0, 0, 0),  # Point A
        Position(0, 0, 0),  # Point B (same as A)
        Position(1, 0, 0),  # Point C (approx 111000km from A/B)
        Position(1, 1, 0),  # Point D
    ]
    route = Route(positions=positions)

    dist_ab = 0.0  # haversine_distance(positions[0], positions[1])
    dist_bc = haversine_distance(positions[1], positions[2])  # Approx 111000.195 km
    dist_cd = haversine_distance(
        positions[2], positions[3]
    )  # Approx 111000.035 km at lat 1
    # (cos(radians(1)) * 111000.195) - more complex actually
    # Let's use simpler points for exact known values or rely on internal haversine.
    # For this test, we trust haversine_distance and check accumulation.

    # Re-evaluate points for easier manual verification if possible, or trust the internal function.
    # Let's make points that are easier to reason about.
    # P0: (0,0)
    # P1: (0,0) -> dist = 0
    # P2: (1,0) -> dist from P1 = haversine( (0,0), (1,0) ) approx 111000.195 km
    # P3: (1,0) -> dist from P2 = 0

    positions_simple = [
        Position(0, 0, 0),  # P0
        Position(0, 0, 0),  # P1
        Position(1, 0, 0),  # P2
        Position(1, 0, 0),  # P3
    ]
    route_simple = Route(positions=positions_simple)

    d0 = 0.0
    d1 = d0 + haversine_distance(
        positions_simple[0], positions_simple[1]
    )  # Should be 0
    d2 = d1 + haversine_distance(positions_simple[1], positions_simple[2])
    d3 = d2 + haversine_distance(
        positions_simple[2], positions_simple[3]
    )  # Should be 0

    expected_distances = [d0, d1, d2, d3]

    actual_distances = route_simple.get_cumulative_distances()

    assert len(actual_distances) == 4
    assert actual_distances == pytest.approx(expected_distances)

    # A slightly more complex case
    positions_varied = [
        Position(latitude=0, longitude=0, elevation=0),  # P1
        Position(latitude=1, longitude=0, elevation=0),  # P2
        Position(latitude=1, longitude=1, elevation=0),  # P3
    ]
    route_varied = Route(positions=positions_varied)

    dist1 = 0.0
    dist2 = dist1 + haversine_distance(positions_varied[0], positions_varied[1])
    dist3 = dist2 + haversine_distance(positions_varied[1], positions_varied[2])

    expected_distances_varied = [dist1, dist2, dist3]
    actual_distances_varied = route_varied.get_cumulative_distances()

    assert actual_distances_varied == pytest.approx(expected_distances_varied)


def test_get_cumulative_distances_memoization():
    route = Route(positions=[Position(0, 0, 0), Position(1, 1, 0)])

    distances1 = route.get_cumulative_distances()
    assert route._cumulative_distances is not None  # Internal check

    distances2 = route.get_cumulative_distances()
    assert distances1 is distances2  # Should be the same list object due to memoization


# Tests for route_spans_overlap function
# RouteSpan is imported from brunnels.brunnel
# route_spans_overlap is imported from brunnels.route


def test_route_spans_overlap_true():
    span1 = RouteSpan(start_distance_km=0.0, end_distance_km=10.0)
    span2 = RouteSpan(start_distance_km=5.0, end_distance_km=15.0)
    assert route_spans_overlap(span1, span2) is True
    assert route_spans_overlap(span2, span1) is True  # Order shouldn't matter


def test_route_spans_overlap_false():
    span1 = RouteSpan(start_distance_km=0.0, end_distance_km=10.0)
    span2 = RouteSpan(start_distance_km=10.1, end_distance_km=15.0)
    assert route_spans_overlap(span1, span2) is False
    assert route_spans_overlap(span2, span1) is False


def test_route_spans_overlap_adjacent_touching():
    # Spans are considered overlapping if start_distance <= end_distance and vice-versa
    span1 = RouteSpan(start_distance_km=0.0, end_distance_km=10.0)
    span2 = RouteSpan(start_distance_km=10.0, end_distance_km=15.0)  # Touches at 10.0
    assert route_spans_overlap(span1, span2) is True
    assert route_spans_overlap(span2, span1) is True


def test_route_spans_overlap_one_contains_another():
    span_outer = RouteSpan(start_distance_km=0.0, end_distance_km=20.0)
    span_inner = RouteSpan(start_distance_km=5.0, end_distance_km=15.0)
    assert route_spans_overlap(span_outer, span_inner) is True
    assert route_spans_overlap(span_inner, span_outer) is True


def test_route_spans_overlap_identical_spans():
    span1 = RouteSpan(start_distance_km=0.0, end_distance_km=10.0)
    span2 = RouteSpan(start_distance_km=0.0, end_distance_km=10.0)
    assert route_spans_overlap(span1, span2) is True


def test_route_spans_overlap_point_span_within():
    # A span that is effectively a point
    span_outer = RouteSpan(start_distance_km=0.0, end_distance_km=10.0)
    span_point = RouteSpan(start_distance_km=5.0, end_distance_km=5.0)
    assert route_spans_overlap(span_outer, span_point) is True
    assert route_spans_overlap(span_point, span_outer) is True


def test_route_spans_overlap_point_span_at_edge():
    span_outer = RouteSpan(start_distance_km=0.0, end_distance_km=10.0)
    span_point_edge = RouteSpan(start_distance_km=10.0, end_distance_km=10.0)
    assert route_spans_overlap(span_outer, span_point_edge) is True
    assert route_spans_overlap(span_point_edge, span_outer) is True


def test_route_spans_overlap_point_span_outside():
    span_outer = RouteSpan(start_distance_km=0.0, end_distance_km=10.0)
    span_point_outside = RouteSpan(start_distance_km=10.1, end_distance_km=10.1)
    assert route_spans_overlap(span_outer, span_point_outside) is False
    assert route_spans_overlap(span_point_outside, span_outer) is False


# Tests for Route.find_brunnels method
class TestFindBrunnels:  # Using a class for grouping related tests

    @patch("brunnels.route.logger")  # Target logger in route.py
    @patch("brunnels.route.query_overpass_brunnels")
    def test_find_brunnels_logging_detailed_filter_reasons(
        self, mock_query_overpass, mock_logger
    ):
        # 1. Set up a simple Route
        # Making route points far apart to simplify containment logic for non-filtered items;
        # for this test, we mostly care about tag filtering log.
        route = Route(positions=[Position(0, 0, 0), Position(10, 10, 0)])

        # 2. Prepare mock way_data to trigger various FilterReasons
        mock_way_data = [
            {
                "id": 1,
                "type": "way",
                "tags": {"bicycle": "no", "highway": "path"},
                "geometry": [{"lat": 0.1, "lon": 0.1}, {"lat": 0.2, "lon": 0.2}],
            },  # BICYCLE_NO
            {
                "id": 2,
                "type": "way",
                "tags": {"waterway": "river"},
                "geometry": [{"lat": 1.1, "lon": 1.1}, {"lat": 1.2, "lon": 1.2}],
            },  # WATERWAY
            {
                "id": 3,
                "type": "way",
                "tags": {"railway": "rail", "service": "mainline"},
                "geometry": [{"lat": 2.1, "lon": 2.1}, {"lat": 2.2, "lon": 2.2}],
            },  # RAILWAY
            # This one should not be filtered by tags initially, but might be filtered by containment/alignment.
            # To ensure it doesn't complicate the tag filtering log count, let's make its geometry far away or very short.
            # For this test, we focus on the tag-based filter counts.
            {
                "id": 4,
                "type": "way",
                "tags": {"highway": "residential"},
                "geometry": [{"lat": 30.0, "lon": 30.0}, {"lat": 30.1, "lon": 30.1}],
            },  # Not filtered by tags, likely not contained.
            {
                "id": 5,
                "type": "way",
                "tags": {"bicycle": "dismount", "highway": "cycleway"},
                "geometry": [{"lat": 0.3, "lon": 0.3}, {"lat": 0.4, "lon": 0.4}],
            },  # BICYCLE_DISMOUNT
        ]

        # Configure mock query_overpass_brunnels
        mock_query_overpass.return_value = mock_way_data

        # Configure find_contained_brunnels to not interfere too much, or ensure items filtered by tags stay that way
        # The actual BrunnelWay objects will be created. We need to ensure their filter_reason is set as expected.
        # The logic inside find_brunnels will call BrunnelWay.from_overpass_data.
        # If a brunnel is tag-filtered, its filter_reason is set there.
        # find_contained_brunnels only processes brunnels with FilterReason.NONE.

        # 3. Call find_brunnels
        route.find_brunnels(
            bbox_buffer=1000,  # meters, large enough to find ways from Overpass query
            route_buffer=50,  # meters, for containment check
            bearing_tolerance_degrees=30,
            enable_tag_filtering=True,
            keep_polygons=False,
        )

        # 4. Construct the expected log message string
        # Based on mock_way_data:
        # - 1 BICYCLE_NO
        # - 1 WATERWAY
        # - 1 RAILWAY
        # Total = 3 tag-filtered brunnels.
        # The non-tag-filtered one (id:4) will be processed for containment.
        # If it's not contained, it gets FilterReason.NOT_CONTAINED. This happens *after* the tag filtering log.
        # So, the log message we are testing should only reflect the initial tag-based filtering.

        expected_total_filtered = 3

        # Iterate through logger calls to find the one we're interested in
        found_log_call = False
        for call_args in mock_logger.debug.call_args_list:
            log_message = call_args[0][0]  # First argument of the call
            if (
                "brunnels filtered" in log_message
                and "will show greyed out" in log_message
            ):
                found_log_call = True
                # Check total count
                assert f"{expected_total_filtered} brunnels filtered" in log_message
                break

        assert (
            found_log_call
        ), "The expected debug log message for filtered brunnels was not found."

    @patch("brunnels.route.logger")
    @patch("brunnels.route.query_overpass_brunnels")
    def test_find_brunnels_logging_no_tag_filtered_brunnels(
        self, mock_query_overpass, mock_logger
    ):
        route = Route(positions=[Position(0, 0, 0), Position(10, 10, 0)])
        mock_way_data = [
            {
                "id": 1,
                "type": "way",
                "tags": {"highway": "residential"},
                "geometry": [{"lat": 0.1, "lon": 0.1}],
            },
            {
                "id": 2,
                "type": "way",
                "tags": {"bridge": "yes"},
                "geometry": [{"lat": 1.1, "lon": 1.1}],
            },
        ]
        mock_query_overpass.return_value = mock_way_data

        route.find_brunnels(
            bbox_buffer=1000,
            route_buffer=50,
            bearing_tolerance_degrees=30,
            enable_tag_filtering=True,
            keep_polygons=False,
        )

        # Assert that the specific log message about tag-filtered brunnels is NOT called
        for call_args in mock_logger.debug.call_args_list:
            log_message = call_args[0][0]
            assert not (
                "brunnels filtered" in log_message
                and "will show greyed out" in log_message
            )

    @patch("brunnels.route.logger")
    @patch("brunnels.route.query_overpass_brunnels")
    def test_find_brunnels_tag_filtering_disabled_logging(
        self, mock_query_overpass, mock_logger
    ):
        route = Route(positions=[Position(0, 0, 0), Position(10, 10, 0)])
        mock_way_data = [  # Same data that would be filtered if enabled
            {
                "id": 1,
                "type": "way",
                "tags": {"bicycle": "no"},
                "geometry": [{"lat": 0.1, "lon": 0.1}],
            },
        ]
        mock_query_overpass.return_value = mock_way_data

        route.find_brunnels(
            bbox_buffer=1000,
            route_buffer=50,
            bearing_tolerance_degrees=30,
            enable_tag_filtering=False,  # Tag filtering disabled
            keep_polygons=False,
        )

        # Assert that the specific log message about tag-filtered brunnels is NOT called
        for call_args in mock_logger.debug.call_args_list:
            log_message = call_args[0][0]
            assert not (
                "brunnels filtered" in log_message
                and "will show greyed out" in log_message
            )
