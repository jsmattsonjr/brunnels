import pytest
import os
from io import StringIO
import tempfile  # Add this to the imports at the top of the file
import math
import logging  # Added for logger mocking
from unittest.mock import patch, MagicMock  # Added for mocking
import collections  # Added for Counter, though not directly used in assertions here

from src.brunnels.config import BrunnelsConfig
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
    assert len(route.trackpoints) == 2
    assert route.trackpoints[0] == {
        "latitude": 40.7128,
        "longitude": -74.0060,
        "elevation": 10.0,
    }
    assert route.trackpoints[1] == {
        "latitude": 40.7580,
        "longitude": -73.9855,
        "elevation": 12.0,
    }


def test_from_gpx_valid_single_track_multi_segment():
    gpx_str = gpx_content(
        [
            [(40.7128, -74.0060, 10.0)],
            [(40.7580, -73.9855, 12.0), (40.7589, -73.9845, 13.0)],
        ]
    )
    route = Route.from_gpx(StringIO(gpx_str))
    assert len(route.trackpoints) == 3
    assert route.trackpoints[0] == {
        "latitude": 40.7128,
        "longitude": -74.0060,
        "elevation": 10.0,
    }
    assert route.trackpoints[1] == {
        "latitude": 40.7580,
        "longitude": -73.9855,
        "elevation": 12.0,
    }
    assert route.trackpoints[2] == {
        "latitude": 40.7589,
        "longitude": -73.9845,
        "elevation": 13.0,
    }


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
    assert len(route.trackpoints) == 3
    assert route.trackpoints[0] == {
        "latitude": 40.7128,
        "longitude": -74.0060,
        "elevation": 10.0,
    }
    assert route.trackpoints[1] == {
        "latitude": 40.7580,
        "longitude": -73.9855,
        "elevation": 12.0,
    }
    assert route.trackpoints[2] == {
        "latitude": 40.7589,
        "longitude": -73.9845,
        "elevation": 13.0,
    }


def test_from_gpx_point_without_elevation():
    gpx_str = gpx_content([[(40.7128, -74.0060, None), (40.7580, -73.9855, 12.0)]])
    route = Route.from_gpx(StringIO(gpx_str))
    assert len(route.trackpoints) == 2
    assert route.trackpoints[0] == {
        "latitude": 40.7128,
        "longitude": -74.0060,
        "elevation": None,
    }
    assert route.trackpoints[1] == {
        "latitude": 40.7580,
        "longitude": -73.9855,
        "elevation": 12.0,
    }


def test_from_gpx_empty_no_tracks():
    # GPX file with no tracks
    gpx_str = gpx_content([])  # Pass empty list to helper
    route = Route.from_gpx(StringIO(gpx_str))
    assert len(route.trackpoints) == 0


def test_from_gpx_empty_track_no_segments():
    # GPX file with a track but no segments
    gpx_start = """<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="pytest" xmlns="http://www.topografix.com/GPX/1/1" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://www.topografix.com/GPX/1/1 http://www.topografix.com/GPX/1/1/gpx.xsd">
<trk></trk>
</gpx>"""
    route = Route.from_gpx(StringIO(gpx_start))
    assert len(route.trackpoints) == 0


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
    assert len(route.trackpoints) == 0
    # Also test with helper if it produces valid empty segment
    route_helper = Route.from_gpx(StringIO(gpx_content([[[]]])))
    assert len(route_helper.trackpoints) == 0


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
        assert len(route.trackpoints) == 2
        assert route.trackpoints[0] == {
            "latitude": 40.7128,
            "longitude": -74.0060,
            "elevation": 10.0,
        }
        assert route.trackpoints[1] == {
            "latitude": 40.7580,
            "longitude": -73.9855,
            "elevation": 12.0,
        }
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
        assert len(route.trackpoints) == 0  # Route class handles empty trackpoints list
    except RouteValidationError:
        pytest.fail("RouteValidationError raised unexpectedly for an empty route.")


# Tests for Route.get_bbox


def test_get_bbox_empty_route():
    route = Route(trackpoints=[])
    with pytest.raises(ValueError) as excinfo:
        route.get_bbox()
    assert "empty route" in str(excinfo.value).lower()


def test_get_bbox_single_point_route_default_buffer():
    # For a single point, buffer calculation is key.
    # 1 deg lat ~ 111000 m. Buffer is 10 m by default.
    # So lat_buffer is 10/111000.0
    # lon_buffer depends on latitude. At lat 0, it's also 10/111000.0
    trackpoint_data = {"latitude": 0, "longitude": 0, "elevation": 0}
    route = Route(trackpoints=[trackpoint_data])

    # Expected buffer values for 0.0 buffer (new default)
    # For a single point, min_lat=max_lat=tp_lat, min_lon=max_lon=tp_lon
    expected_bbox_0_buffer = (
        trackpoint_data["latitude"],
        trackpoint_data["longitude"],
        trackpoint_data["latitude"],
        trackpoint_data["longitude"],
    )

    bbox = route.get_bbox()  # Default buffer is now 0.0
    assert bbox == pytest.approx(expected_bbox_0_buffer)

    # Test with a specific buffer (e.g., 10.0m, which was the old default)
    buffer_10m = 10.0
    lat_buffer_deg_10m = buffer_10m / 111000.0
    lon_buffer_deg_10m = buffer_10m / (111000.0)  # cos(radians(0)) = 1

    expected_bbox_10m_buffer = (
        max(-90.0, trackpoint_data["latitude"] - lat_buffer_deg_10m),
        max(-180.0, trackpoint_data["longitude"] - lon_buffer_deg_10m),
        min(90.0, trackpoint_data["latitude"] + lat_buffer_deg_10m),
        min(180.0, trackpoint_data["longitude"] + lon_buffer_deg_10m),
    )
    bbox_10m = route.get_bbox(buffer=buffer_10m)
    assert bbox_10m == pytest.approx(expected_bbox_10m_buffer)


def test_get_bbox_single_point_route_custom_buffer():
    trackpoint_data = {
        "latitude": 45,
        "longitude": 45,
        "elevation": 0,
    }  # Use a non-zero latitude
    route = Route(trackpoints=[trackpoint_data])

    # Base 0-buffer bbox for this single point
    min_lat, min_lon, max_lat, max_lon = (
        trackpoint_data["latitude"],
        trackpoint_data["longitude"],
        trackpoint_data["latitude"],
        trackpoint_data["longitude"],
    )

    buffer_m = 5.0
    # avg_lat for buffer calculation is from the 0-buffer bbox
    avg_lat_for_buffer_calc = (min_lat + max_lat) / 2
    lat_buffer_deg = buffer_m / 111000.0
    lon_buffer_deg = buffer_m / (
        111000.0 * abs(math.cos(math.radians(avg_lat_for_buffer_calc)))
    )

    expected_bbox_custom = (
        max(-90.0, min_lat - lat_buffer_deg),
        max(-180.0, min_lon - lon_buffer_deg),
        min(90.0, max_lat + lat_buffer_deg),
        min(180.0, max_lon + lon_buffer_deg),
    )

    bbox = route.get_bbox(buffer=buffer_m)
    assert bbox == pytest.approx(expected_bbox_custom)


def test_get_bbox_multi_point_route_no_buffer_implicitly_zero():
    trackpoints_data = [
        {"latitude": 0, "longitude": 0, "elevation": 0},  # min_lat=0, max_lat=1
        {"latitude": 1, "longitude": 1, "elevation": 0},  # min_lon=0, max_lon=1
    ]
    route = Route(trackpoints=trackpoints_data)

    # Expected 0-buffer bbox
    expected_bbox_0_buffer = (0.0, 0.0, 1.0, 1.0)

    bbox = route.get_bbox()  # Default buffer is 0.0
    assert bbox == pytest.approx(expected_bbox_0_buffer)

    # Also test explicitly with buffer=0.0
    bbox_explicit_0 = route.get_bbox(buffer=0.0)
    assert bbox_explicit_0 == pytest.approx(expected_bbox_0_buffer)


def test_get_bbox_multi_point_route_larger_buffer():
    trackpoints_data = [
        {"latitude": 10, "longitude": 10, "elevation": 0},
        {"latitude": 12, "longitude": 13, "elevation": 0},
    ]
    route = Route(trackpoints=trackpoints_data)

    # Base 0-buffer bbox
    min_lat, min_lon, max_lat, max_lon = (10.0, 10.0, 12.0, 13.0)

    buffer_m = 100.0  # Larger buffer
    avg_lat_for_buffer_calc = (min_lat + max_lat) / 2  # (10+12)/2 = 11.0
    lat_buffer_deg = buffer_m / 111000.0
    lon_buffer_deg = buffer_m / (
        111000.0 * abs(math.cos(math.radians(avg_lat_for_buffer_calc)))
    )

    expected_bbox_custom = (
        max(-90.0, min_lat - lat_buffer_deg),
        max(-180.0, min_lon - lon_buffer_deg),
        min(90.0, max_lat + lat_buffer_deg),
        min(180.0, max_lon + lon_buffer_deg),
    )
    bbox = route.get_bbox(buffer=buffer_m)
    assert bbox == pytest.approx(expected_bbox_custom)


def test_get_bbox_memoization():
    trackpoints_data = [
        {"latitude": 0, "longitude": 0, "elevation": 0},
        {"latitude": 1, "longitude": 1, "elevation": 0},
    ]
    route = Route(trackpoints=trackpoints_data)

    # Expected 0-buffer (base) bbox
    expected_base_bbox = (0.0, 0.0, 1.0, 1.0)

    # Call get_bbox with a buffer. _bbox should store the 0-buffer version.
    buffer1_val = 1.0
    # Calculate expected for buffer1_val based on expected_base_bbox
    avg_lat_base = (expected_base_bbox[0] + expected_base_bbox[2]) / 2.0
    lat_buf1_deg = buffer1_val / 111000.0
    lon_buf1_deg = buffer1_val / (111000.0 * abs(math.cos(math.radians(avg_lat_base))))
    expected_bbox_buffer1 = (
        max(-90.0, expected_base_bbox[0] - lat_buf1_deg),
        max(-180.0, expected_base_bbox[1] - lon_buf1_deg),
        min(90.0, expected_base_bbox[2] + lat_buf1_deg),
        min(180.0, expected_base_bbox[3] + lon_buf1_deg),
    )

    bbox_buffer1 = route.get_bbox(buffer=buffer1_val)
    assert bbox_buffer1 == pytest.approx(expected_bbox_buffer1)
    assert route._bbox == pytest.approx(expected_base_bbox)  # _bbox is always 0-buffer

    # Call get_bbox with the same buffer, should return an equal result (on-the-fly calculation)
    bbox_buffer1_again = route.get_bbox(buffer=buffer1_val)
    assert bbox_buffer1_again == pytest.approx(expected_bbox_buffer1)
    assert route._bbox == pytest.approx(expected_base_bbox)  # _bbox remains 0-buffer

    # Call get_bbox with a different buffer.
    buffer2_val = 2.0
    lat_buf2_deg = buffer2_val / 111000.0
    lon_buf2_deg = buffer2_val / (111000.0 * abs(math.cos(math.radians(avg_lat_base))))
    expected_bbox_buffer2 = (
        max(-90.0, expected_base_bbox[0] - lat_buf2_deg),
        max(-180.0, expected_base_bbox[1] - lon_buf2_deg),
        min(90.0, expected_base_bbox[2] + lat_buf2_deg),
        min(180.0, expected_base_bbox[3] + lon_buf2_deg),
    )
    bbox_buffer2 = route.get_bbox(buffer=buffer2_val)
    assert bbox_buffer2 == pytest.approx(expected_bbox_buffer2)
    assert route._bbox == pytest.approx(expected_base_bbox)  # _bbox still 0-buffer
    assert bbox_buffer2 != pytest.approx(bbox_buffer1)

    # Call get_bbox with 0 buffer. Should return the memoized route._bbox.
    bbox_0_buffer = route.get_bbox(buffer=0.0)
    assert bbox_0_buffer == pytest.approx(expected_base_bbox)
    assert bbox_0_buffer is route._bbox  # Should be the same object

    # Call get_bbox with default buffer (which is 0). Should also return memoized route._bbox.
    bbox_default_buffer = route.get_bbox()
    assert bbox_default_buffer == pytest.approx(expected_base_bbox)
    assert bbox_default_buffer is route._bbox  # Should be the same object

    # Ensure _bbox_buffer field does not exist
    assert not hasattr(route, "_bbox_buffer")


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
        route = Route(
            trackpoints=[
                {"latitude": 0, "longitude": 0, "elevation": 0},
                {"latitude": 10, "longitude": 10, "elevation": 0},
            ]
        )

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
        config = BrunnelsConfig()
        config.bbox_buffer = 1000
        config.route_buffer = 50
        config.bearing_tolerance = 30
        route.find_brunnels(config)

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
        route = Route(
            trackpoints=[
                {"latitude": 0, "longitude": 0, "elevation": 0},
                {"latitude": 10, "longitude": 10, "elevation": 0},
            ]
        )
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

        config = BrunnelsConfig()
        config.bbox_buffer = 1000
        config.route_buffer = 50
        config.bearing_tolerance = 30
        route.find_brunnels(config)

        # Assert that the specific log message about tag-filtered brunnels is NOT called
        for call_args in mock_logger.debug.call_args_list:
            log_message = call_args[0][0]
            assert not (
                "brunnels filtered" in log_message
                and "will show greyed out" in log_message
            )

    @patch("brunnels.route.logger")
    @patch("brunnels.route.query_overpass_brunnels")
    def test_find_brunnels_tag_filtering_now_always_on_logging(
        self, mock_query_overpass, mock_logger
    ):
        route = Route(
            trackpoints=[
                {"latitude": 0, "longitude": 0, "elevation": 0},
                {"latitude": 10, "longitude": 10, "elevation": 0},
            ]
        )
        mock_way_data = [  # Data that will be filtered
            {
                "id": 1,
                "type": "way",
                "tags": {"bicycle": "no"},  # This tag will cause filtering
                "geometry": [{"lat": 0.1, "lon": 0.1}],
            },
        ]
        mock_query_overpass.return_value = mock_way_data

        config = BrunnelsConfig()
        config.bbox_buffer = 1000
        config.route_buffer = 50
        config.bearing_tolerance = 30
        route.find_brunnels(config)

        # Assert that the specific log message about tag-filtered brunnels IS called
        # because filtering is now always on.
        expected_total_filtered = 1  # Only one item, and it's filtered
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
        ), "The expected debug log message for filtered brunnels was not found (it should be present as filtering is always on)."


def test_calculate_distances_empty_route():
    """Test calculate_distances with empty route."""
    route = Route(trackpoints=[])
    route.calculate_distances()
    assert len(route.trackpoints) == 0


def test_calculate_distances_single_point():
    """Test calculate_distances with single trackpoint."""
    route = Route(trackpoints=[{"latitude": 0, "longitude": 0, "elevation": 0}])
    route.calculate_distances()
    assert len(route.trackpoints) == 1
    assert route.trackpoints[0]["track_distance"] == 0.0


def test_calculate_distances_multi_points():
    """Test calculate_distances with multiple trackpoints."""
    trackpoints = [
        {"latitude": 0, "longitude": 0, "elevation": 0},
        {"latitude": 0, "longitude": 0, "elevation": 0},  # Same position
        {"latitude": 1, "longitude": 0, "elevation": 0},  # Different position
        {"latitude": 1, "longitude": 1, "elevation": 0},  # Different position
    ]
    route = Route(trackpoints=trackpoints)
    route.calculate_distances()

    # First point should be 0
    assert route.trackpoints[0]["track_distance"] == 0.0

    # Second point should be 0 (same position as first)
    assert route.trackpoints[1]["track_distance"] == 0.0

    # Third point should be > 0 (different position)
    assert route.trackpoints[2]["track_distance"] > 0.0

    # Fourth point should be > third point distance
    assert (
        route.trackpoints[3]["track_distance"] > route.trackpoints[2]["track_distance"]
    )

    # Manually verify using haversine_distance
    expected_dist_2 = haversine_distance(Position(0, 0, 0), Position(1, 0, 0))
    expected_dist_3 = expected_dist_2 + haversine_distance(
        Position(1, 0, 0), Position(1, 1, 0)
    )

    assert route.trackpoints[2]["track_distance"] == pytest.approx(expected_dist_2)
    assert route.trackpoints[3]["track_distance"] == pytest.approx(expected_dist_3)


def test_calculate_distances_with_none_elevation():
    """Test calculate_distances with None elevation values."""
    trackpoints = [
        {"latitude": 0, "longitude": 0, "elevation": None},
        {"latitude": 1, "longitude": 0, "elevation": 10.0},
    ]
    route = Route(trackpoints=trackpoints)
    route.calculate_distances()

    assert route.trackpoints[0]["track_distance"] == 0.0
    assert route.trackpoints[1]["track_distance"] > 0.0

    # Should be same as calculated manually
    expected_distance = haversine_distance(Position(0, 0, None), Position(1, 0, 10.0))
    assert route.trackpoints[1]["track_distance"] == pytest.approx(expected_distance)
