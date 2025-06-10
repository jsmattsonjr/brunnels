import pytest
from shapely.geometry import LineString, Polygon

from brunnels.brunnel import Brunnel, BrunnelType, FilterReason, RouteSpan
from brunnels.brunnel_way import BrunnelWay
from brunnels.geometry import Position
from brunnels.route import Route
from brunnels.geometry_utils import calculate_bearing  # For reference in tests
from brunnels.compound_brunnel_way import CompoundBrunnelWay


# Helper function to create a BrunnelWay instance for testing
def create_brunnel_way(
    brunnel_id: int,
    nodes: list[int],
    tags: dict[str, str],
    brunnel_type: BrunnelType = BrunnelType.BRIDGE,
    coords: list[Position] | None = None,
) -> BrunnelWay:
    if coords is None:
        coords = [Position(0, 0), Position(0, 1)]  # Default coordinates
    metadata = {"id": brunnel_id, "nodes": nodes, "tags": tags}
    return BrunnelWay(
        coords=coords,
        metadata=metadata,
        brunnel_type=brunnel_type,
        # filter_reason will be determined by should_filter
    )


# Tests for BrunnelWay.should_filter
@pytest.mark.parametrize(
    "tags, expected_reason, nodes_override",
    [
        # Bicycle=no
        ({"bicycle": "no"}, FilterReason.BICYCLE_NO, None),
        # Waterway
        ({"waterway": "river"}, FilterReason.WATERWAY, None),
        # Railway (not abandoned)
        ({"railway": "rail"}, FilterReason.RAILWAY, None),
        # Closed way
        ({}, FilterReason.CLOSED_WAY, [1, 2, 3, 1]),
        (
            {"highway": "footway"},
            FilterReason.CLOSED_WAY,
            [1, 2, 3, 1],
        ),  # Closed way with other tags
        # Open way cases
        ({}, FilterReason.NONE, [1, 2]),  # Default, open way
        (
            {"highway": "footway"},
            FilterReason.NONE,
            [1, 2],
        ),  # Open way with other tags
    ],
)
def test_should_filter_various_reasons(
    tags: dict[str, str],
    expected_reason: FilterReason,
    nodes_override: list[int] | None,
):
    nodes = (
        nodes_override if nodes_override is not None else [1, 2]
    )  # Default for non-closed cases
    brunnel_way = create_brunnel_way(1, nodes, tags)
    assert BrunnelWay.should_filter(brunnel_way.metadata) == expected_reason


# Specific tests for closed way filtering
def test_should_filter_closed_way_filter_out():
    nodes_closed = [1, 2, 3, 1]  # Closed way
    brunnel_way_closed = create_brunnel_way(1, nodes_closed, {})
    assert (
        BrunnelWay.should_filter(brunnel_way_closed.metadata) == FilterReason.CLOSED_WAY
    )


@pytest.mark.parametrize(
    "tags",
    [
        # No relevant tags
        {},
        {"name": "Test Bridge"},
        # Bicycle=yes/designated/etc.
        {"bicycle": "yes"},
        {"bicycle": "designated"},
        # Cycleway
        {"highway": "cycleway"},
        {"cycleway": "track"},  # Other cycleway tags also imply bicycle use
        # Abandoned railway
        {"railway": "abandoned"},
        {"railway": "abandoned", "bicycle": "dismount"},  # bicycle=dismount is not "no"
        # Highway residential (and other common types that shouldn't be filtered by default)
        {"highway": "residential"},
        {"highway": "service"},
        # Combination of tags where bicycle is not "no"
        {
            "highway": "road",
            "bicycle": "yes",
            "waterway": "canal",
        },  # waterway is ignored due to bicycle=yes
        {
            "railway": "preserved",
            "bicycle": "permissive",
        },  # railway ignored due to bicycle=permissive
    ],
)
def test_should_not_filter(tags: dict[str, str]):
    # These tests assume open ways. The create_brunnel_way helper uses [1,2] by default.
    brunnel_way = create_brunnel_way(1, [1, 2], tags)
    assert BrunnelWay.should_filter(brunnel_way.metadata) == FilterReason.NONE


# Test for specific priority: bicycle tag overrides others
def test_should_filter_priority_bicycle_over_waterway():
    tags = {"bicycle": "yes", "waterway": "river"}
    brunnel_way = create_brunnel_way(1, [1, 2], tags)
    assert BrunnelWay.should_filter(brunnel_way.metadata) == FilterReason.NONE


def test_should_filter_priority_bicycle_no_over_cycleway():
    tags = {"bicycle": "no", "highway": "cycleway"}
    brunnel_way = create_brunnel_way(1, [1, 2], tags)
    assert BrunnelWay.should_filter(brunnel_way.metadata) == FilterReason.BICYCLE_NO


def test_should_filter_priority_cycleway_over_waterway():
    tags = {"highway": "cycleway", "waterway": "river"}
    brunnel_way = create_brunnel_way(1, [1, 2], tags)
    assert BrunnelWay.should_filter(brunnel_way.metadata) == FilterReason.NONE


def test_should_filter_priority_waterway_over_railway():  # Though usually not combined
    tags = {"waterway": "river", "railway": "rail"}
    brunnel_way = create_brunnel_way(1, [1, 2], tags)
    # Based on current logic, waterway is checked before railway
    assert BrunnelWay.should_filter(brunnel_way.metadata) == FilterReason.WATERWAY


def test_should_filter_empty_tags():
    brunnel_way = create_brunnel_way(1, [1, 2], {})
    assert BrunnelWay.should_filter(brunnel_way.metadata) == FilterReason.NONE


# Tests for BrunnelWay.determine_type
@pytest.mark.parametrize(
    "tags, expected_type",
    [
        # Tunnel cases
        ({"tunnel": "yes"}, BrunnelType.TUNNEL),
        ({"tunnel": "true"}, BrunnelType.TUNNEL),
        ({"tunnel": "culvert"}, BrunnelType.TUNNEL),
        (
            {"bridge": "yes", "tunnel": "yes"},
            BrunnelType.TUNNEL,
        ),  # Tunnel tag takes precedence
        ({"tunnel": "building_passage"}, BrunnelType.TUNNEL),
        # Bridge cases (default if not tunnel)
        ({}, BrunnelType.BRIDGE),  # Default to bridge if no tunnel tag
        ({"bridge": "yes"}, BrunnelType.BRIDGE),
        ({"bridge": "viaduct"}, BrunnelType.BRIDGE),
        (
            {"man_made": "bridge"},
            BrunnelType.BRIDGE,
        ),  # Common alternative tag for bridge
        ({"tunnel": "no"}, BrunnelType.BRIDGE),  # Explicitly not a tunnel
        ({"tunnel": "false"}, BrunnelType.BRIDGE),
    ],
)
def test_determine_type(tags: dict[str, str], expected_type: BrunnelType):
    # The specific BrunnelWay instance details (id, nodes, coords) don't matter for determine_type
    metadata = {"tags": tags}
    assert BrunnelWay.determine_type(metadata) == expected_type


# Mock Brunnel class for testing
class MockBrunnel(Brunnel):
    def __init__(
        self,
        brunnel_type: BrunnelType,
        coords: list[Position],
        brunnel_id: str = "test_brunnel",
    ):
        super().__init__(brunnel_type)
        self._coords = coords
        self._id = brunnel_id

    @property
    def coordinate_list(self) -> list[Position]:
        return self._coords

    def to_html(self) -> str:
        return "Mock Brunnel HTML"

    def get_id(self) -> str:
        return self._id

    def get_display_name(self) -> str:
        return "Mock Brunnel"

    def get_short_description(self) -> str:
        return f"{self.brunnel_type.value.capitalize()}: Mock Brunnel ({self.get_id()})"


# Tests for Brunnel.is_contained_by
@pytest.fixture
def simple_route_geometry() -> Polygon:
    # A simple square route buffer polygon from (0,0) to (2,2)
    # Route points could be (0.5, 0.5) to (1.5, 1.5) with a buffer
    # For simplicity, directly define the polygon
    return Polygon([(0, 0), (0, 2), (2, 2), (2, 0)])


@pytest.fixture
def complex_route_geometry() -> Polygon:
    # A more complex L-shaped polygon
    return Polygon([(0, 0), (0, 3), (1, 3), (1, 1), (3, 1), (3, 0)])


def test_is_contained_by_true_simple_route(simple_route_geometry: Polygon):
    # Brunnel completely inside the square
    brunnel_coords = [Position(0.5, 0.5), Position(1.5, 1.5)]
    brunnel = MockBrunnel(BrunnelType.BRIDGE, brunnel_coords)
    assert brunnel.is_contained_by(simple_route_geometry) is True


def test_is_contained_by_false_partially_outside_simple_route(
    simple_route_geometry: Polygon,
):
    # Brunnel partially outside the square
    brunnel_coords = [Position(1.5, 1.5), Position(2.5, 2.5)]
    brunnel = MockBrunnel(BrunnelType.BRIDGE, brunnel_coords)
    assert brunnel.is_contained_by(simple_route_geometry) is False


def test_is_contained_by_false_completely_outside_simple_route(
    simple_route_geometry: Polygon,
):
    # Brunnel completely outside the square
    brunnel_coords = [Position(3, 3), Position(4, 4)]
    brunnel = MockBrunnel(BrunnelType.BRIDGE, brunnel_coords)
    assert brunnel.is_contained_by(simple_route_geometry) is False


def test_is_contained_by_true_on_boundary_simple_route(simple_route_geometry: Polygon):
    # Brunnel on the boundary (Shapely's contains usually means interior)
    # A brunnel line string on the boundary is NOT contained by the polygon.
    # The brunnel must be strictly within.
    brunnel_coords = [Position(0, 0.5), Position(0, 1.5)]  # On the left edge
    brunnel = MockBrunnel(BrunnelType.BRIDGE, brunnel_coords)
    assert brunnel.is_contained_by(simple_route_geometry) is False

    brunnel_coords_inside = [Position(0.1, 0.5), Position(0.1, 1.5)]  # Slightly inside
    brunnel_inside = MockBrunnel(BrunnelType.BRIDGE, brunnel_coords_inside)
    assert brunnel_inside.is_contained_by(simple_route_geometry) is True


def test_is_contained_by_true_complex_route(complex_route_geometry: Polygon):
    # Brunnel completely inside the L-shape
    brunnel_coords = [Position(0.25, 0.25), Position(0.75, 0.75)]  # Vertical part
    brunnel = MockBrunnel(BrunnelType.BRIDGE, brunnel_coords)
    assert brunnel.is_contained_by(complex_route_geometry) is True

    brunnel_coords_horizontal = [
        Position(1.5, 0.25),
        Position(2.5, 0.75),
    ]  # Horizontal part
    brunnel_horizontal = MockBrunnel(BrunnelType.BRIDGE, brunnel_coords_horizontal)
    assert brunnel_horizontal.is_contained_by(complex_route_geometry) is True


def test_is_contained_by_false_complex_route(complex_route_geometry: Polygon):
    # Brunnel crossing the boundary of the L-shape
    brunnel_coords = [
        Position(0.5, 2.5),
        Position(1.5, 2.5),
    ]  # Crosses from inside to outside top part
    brunnel = MockBrunnel(BrunnelType.BRIDGE, brunnel_coords)
    assert brunnel.is_contained_by(complex_route_geometry) is False


def test_is_contained_by_empty_brunnel_coords(simple_route_geometry: Polygon):
    brunnel = MockBrunnel(BrunnelType.BRIDGE, [])
    assert (
        brunnel.is_contained_by(simple_route_geometry) is False
    )  # No linestring to check


def test_is_contained_by_single_point_brunnel(simple_route_geometry: Polygon):
    # A single point brunnel (LineString requires at least two points)
    # The get_linestring method in Geometry will return None for < 2 points.
    brunnel_coords = [Position(1, 1)]
    brunnel = MockBrunnel(BrunnelType.BRIDGE, brunnel_coords)
    assert brunnel.is_contained_by(simple_route_geometry) is False


# Tests for Brunnel.calculate_route_span


# Helper to create a simple mock route
def create_mock_route(positions: list[Position]) -> Route:
    trackpoints = [
        {
            "latitude": pos.latitude,
            "longitude": pos.longitude,
            "elevation": pos.elevation,
        }
        for pos in positions
    ]
    return Route(trackpoints=trackpoints)


@pytest.fixture
def linear_route() -> Route:
    # Route along the x-axis: (0,0) -> (1,0) -> (2,0) -> (3,0) -> (4,0) -> (5,0)
    # Each segment is 1 unit long (approx 111km if these were degrees, but for simplicity, assume unit distance)
    # We will mock haversine for predictable distances if needed, or use simple geometry.
    # For calculate_route_span, it uses find_closest_point_on_route, which relies on cumulative distances.
    # Let's use points where cumulative distances are easy: 0, 1, 2, 3, 4, 5
    return create_mock_route(
        [
            Position(0, 0),
            Position(1, 0),
            Position(2, 0),
            Position(3, 0),
            Position(4, 0),
            Position(5, 0),
        ]
    )


def test_calculate_route_span_brunnel_along_route_segment(linear_route: Route):
    # Brunnel from (1,0) to (2,0) which is exactly the second segment of the route
    brunnel_coords = [Position(1, 0), Position(2, 0)]
    brunnel = MockBrunnel(BrunnelType.BRIDGE, brunnel_coords)

    route_close = create_mock_route(
        [Position(0, 0), Position(0.001, 0), Position(0.002, 0)]
    )
    route_close.calculate_distances()

    brunnel_coords_close = [Position(0.001, 0), Position(0.002, 0)]
    brunnel_close = MockBrunnel(BrunnelType.BRIDGE, brunnel_coords_close)
    route_span = brunnel_close.calculate_route_span(route_close)

    # The coords of the brunnel are exactly on the route points.
    # find_closest_point_on_route for Position(0.001,0) should give cum_dist_close[1]
    # find_closest_point_on_route for Position(0.002,0) should give cum_dist_close[2]
    assert route_span.start_distance_km == pytest.approx(
        route_close.trackpoints[1]["track_distance"]
    )
    assert route_span.end_distance_km == pytest.approx(
        route_close.trackpoints[2]["track_distance"]
    )
    assert route_span.length_km == pytest.approx(
        route_close.trackpoints[2]["track_distance"]
        - route_close.trackpoints[1]["track_distance"]
    )


def test_calculate_route_span_brunnel_offset_from_route(linear_route: Route):
    # Brunnel from (1, 0.1) to (2, 0.1) - offset from the route (0,0) to (5,0)
    # The closest points on the route will be (1,0) and (2,0)
    brunnel_coords = [
        Position(1, 0.1),
        Position(2, 0.1),
    ]  # y is latitude, x is longitude
    brunnel = MockBrunnel(BrunnelType.BRIDGE, brunnel_coords)

    # Let's use a route with more distinct distances for clarity
    # Route: (0,0) -> (10,0) -> (20,0) (longitude varies, latitude is 0)
    # If Position(lon, lat), then (0,0) -> (0.01,0) -> (0.02,0)
    # For simplicity, let's assume points are (lat, lon) as in Position constructor
    route_points = [
        Position(0, 0),
        Position(0, 0.01),
        Position(0, 0.02),
    ]  # Route along equator
    simple_route = create_mock_route(route_points)
    simple_route.calculate_distances()

    # Brunnel points: (0.0001, 0.01), (0.0001, 0.02) - slightly offset in latitude
    brunnel_coords_offset = [Position(0.0001, 0.01), Position(0.0001, 0.02)]
    brunnel_offset = MockBrunnel(BrunnelType.BRIDGE, brunnel_coords_offset)

    route_span = brunnel_offset.calculate_route_span(simple_route)

    # Closest point to (0.0001, 0.01) on route is (0, 0.01) -> distance simple_route.trackpoints[1]["track_distance"]
    # Closest point to (0.0001, 0.02) on route is (0, 0.02) -> distance simple_route.trackpoints[2]["track_distance"]
    assert route_span.start_distance_km == pytest.approx(
        simple_route.trackpoints[1]["track_distance"]
    )
    assert route_span.end_distance_km == pytest.approx(
        simple_route.trackpoints[2]["track_distance"]
    )
    assert route_span.length_km == pytest.approx(
        simple_route.trackpoints[2]["track_distance"]
        - simple_route.trackpoints[1]["track_distance"]
    )


def test_calculate_route_span_brunnel_partially_spans_segment(linear_route: Route):
    # Brunnel from (1.5, 0) to (2.5, 0)
    # Route: (0,0) -> (1,0) -> (2,0) -> (3,0) -> (4,0) -> (5,0) (lat,lon for Position)
    # Let's use the Position(lat,lon) convention
    # Route: (0,0) (0,1) (0,2) (0,3) (0,4) (0,5)
    test_route = create_mock_route(
        [
            Position(0, 0),
            Position(0, 1),
            Position(0, 2),
            Position(0, 3),
            Position(0, 4),
            Position(0, 5),
        ]
    )
    test_route.calculate_distances()

    brunnel_coords = [
        Position(0, 1.5),
        Position(0, 2.5),
    ]  # Brunnel from (0,1.5) to (0,2.5)
    brunnel = MockBrunnel(BrunnelType.BRIDGE, brunnel_coords)
    route_span = brunnel.calculate_route_span(test_route)

    # Closest to (0,1.5) is on segment (0,1)-(0,2). dist_on_route will be d(0,1) + 0.5 * d_segment(1,2)
    # Closest to (0,2.5) is on segment (0,2)-(0,3). dist_on_route will be d(0,2) + 0.5 * d_segment(2,3)
    # This relies on find_closest_point_on_route working correctly for points between route nodes.

    # Let's find these expected distances manually using the cumulative distances
    # For (0, 1.5):
    # Segment is between route.positions[1] (0,1) and route.positions[2] (0,2)
    # Cumulative distance to route.positions[1] is test_cum_dist[1]
    # Length of this segment is test_cum_dist[2] - test_cum_dist[1]
    # The point (0,1.5) is halfway along this segment in terms of coordinates.
    # Assuming linear mapping of distance, expected_start_dist = test_cum_dist[1] + 0.5 * (test_cum_dist[2] - test_cum_dist[1])
    expected_start_dist = (
        test_route.trackpoints[1]["track_distance"]
        + test_route.trackpoints[2]["track_distance"]
    ) / 2.0

    # For (0, 2.5):
    # Segment is between route.positions[2] (0,2) and route.positions[3] (0,3)
    # Cumulative distance to route.positions[2] is test_cum_dist[2]
    # Length of this segment is test_cum_dist[3] - test_cum_dist[2]
    # Expected_end_dist = test_cum_dist[2] + 0.5 * (test_cum_dist[3] - test_cum_dist[2])
    expected_end_dist = (
        test_route.trackpoints[2]["track_distance"]
        + test_route.trackpoints[3]["track_distance"]
    ) / 2.0

    assert route_span.start_distance_km == pytest.approx(expected_start_dist)
    assert route_span.end_distance_km == pytest.approx(expected_end_dist)
    assert route_span.length_km == pytest.approx(
        expected_end_dist - expected_start_dist
    )


def test_calculate_route_span_brunnel_longer_than_route(linear_route: Route):
    # Brunnel from (-1, 0) to (6, 0) - extends beyond the route (0,0) to (5,0)
    # Using (lat,lon) for Position: Brunnel from (0,-1) to (0,6)
    # Route from (0,0) to (0,5)
    test_route = create_mock_route(
        [
            Position(0, 0),
            Position(0, 1),
            Position(0, 2),
            Position(0, 3),
            Position(0, 4),
            Position(0, 5),
        ]
    )
    test_route.calculate_distances()

    brunnel_coords = [Position(0, -1), Position(0, 6)]
    brunnel = MockBrunnel(BrunnelType.BRIDGE, brunnel_coords)
    route_span = brunnel.calculate_route_span(test_route)

    # Closest point to (0,-1) on route is (0,0) -> distance test_cum_dist[0] = 0
    # Closest point to (0,6) on route is (0,5) -> distance test_cum_dist[5] (last point)
    assert route_span.start_distance_km == pytest.approx(
        test_route.trackpoints[0]["track_distance"]
    )
    assert route_span.end_distance_km == pytest.approx(
        test_route.trackpoints[-1]["track_distance"]
    )
    assert route_span.length_km == pytest.approx(
        test_route.trackpoints[-1]["track_distance"]
        - test_route.trackpoints[0]["track_distance"]
    )


# Tests for Brunnel.is_aligned_with_route


@pytest.fixture
def horizontal_route() -> Route:
    # Route from (0,0) to (0,2) - bearing 0 degrees (North) if (lat,lon)
    # If (lon,lat) for geometry funcs, then (0,0) to (2,0) is bearing 90 deg (East)
    # The geometry_utils.calculate_bearing expects (lon1, lat1), (lon2, lat2)
    # So Position(lat,lon) -> (lon,lat) for calculate_bearing
    # Route: P(0,0) -> P(1,0) -> P(2,0) (Eastward if Position(lat,lon) means lat=y, lon=x)
    return create_mock_route(
        [Position(0, 0), Position(0, 1), Position(0, 2)]
    )  # Eastward: lon changes, lat is 0


@pytest.fixture
def vertical_route() -> Route:
    # Route: P(0,0) -> P(0,1) -> P(0,2) (Northward if Position(lat,lon))
    return create_mock_route(
        [Position(0, 0), Position(1, 0), Position(2, 0)]
    )  # Northward: lat changes, lon is 0


# Test cases for Brunnel.is_aligned_with_route
# Note: calculate_bearing(p1, p2) takes points as (lon, lat) tuples.
# Position is (lat, lon). So we need to be careful with coordinate order.
# Brunnel internal coords are List[Position]. find_closest_segments takes these.
# calculate_bearing is called with (brunnel_start.longitude, brunnel_start.latitude), ...


def test_is_aligned_with_route_perfectly_aligned_horizontal(horizontal_route: Route):
    # Horizontal route: P(0,0) to P(0,2) -> lon from 0 to 2, lat = 0. Bearing East (90)
    # Brunnel: P(0,0.5) to P(0,1.5) -> also bearing 90 deg
    brunnel_coords_east = [
        Position(0, 0.5),
        Position(0, 1.5),
    ]  # Brunnel lon from 0.5 to 1.5, lat = 0. Bearing East (90)
    brunnel = MockBrunnel(BrunnelType.BRIDGE, brunnel_coords_east)
    assert brunnel.is_aligned_with_route(horizontal_route, tolerance_degrees=10) is True


def test_is_aligned_with_route_perfectly_aligned_vertical(vertical_route: Route):
    # Vertical route: P(0,0) -> P(2,0) -> lat from 0 to 2, lon = 0. Bearing North (0)
    brunnel_coords = [
        Position(0.5, 0),
        Position(1.5, 0),
    ]  # Brunnel lat from 0.5 to 1.5, lon = 0. Bearing North (0)
    brunnel = MockBrunnel(BrunnelType.BRIDGE, brunnel_coords)
    assert brunnel.is_aligned_with_route(vertical_route, tolerance_degrees=10) is True


def test_is_aligned_with_route_opposite_direction(horizontal_route: Route):
    # Horizontal route: P(0,0) to P(0,2) (East, 90 deg)
    # Brunnel: P(0,1.5) to P(0,0.5) (West, 270 deg) - aligned if +/- 180 is allowed
    brunnel_coords = [Position(0, 1.5), Position(0, 0.5)]
    brunnel = MockBrunnel(BrunnelType.BRIDGE, brunnel_coords)
    # bearings_aligned checks for abs(bearing1 - bearing2) < tol OR abs(bearing1 - bearing2 - 360) < tol OR abs(bearing1 - bearing2 + 360) < tol
    # AND also abs(abs(bearing1 - bearing2) - 180) < tol (for opposite alignment)
    assert brunnel.is_aligned_with_route(horizontal_route, tolerance_degrees=10) is True


def test_is_aligned_with_route_perpendicular(horizontal_route: Route):
    # Horizontal route: P(0,0) to P(0,2) (East, 90 deg)
    # Brunnel: P(0.5,1.0) to P(1.5,1.0) (North, 0 deg, using Position(lat,lon))
    brunnel_coords = [
        Position(0.5, 1.0),
        Position(1.5, 1.0),
    ]  # lat from 0.5 to 1.5, lon = 1.0
    # Brunnel is North (0/360 deg)
    # Route is East (90 deg)
    # Difference is 90 deg.
    brunnel = MockBrunnel(BrunnelType.BRIDGE, brunnel_coords)
    assert (
        brunnel.is_aligned_with_route(horizontal_route, tolerance_degrees=10) is False
    )


def test_is_aligned_with_route_within_tolerance(horizontal_route: Route):
    # Horizontal route: P(0,0) to P(0,2) (East, 90 deg)
    # Brunnel slightly off: e.g., bearing 85 degrees or 95 degrees
    # P(0,0.5) to P(0.1, 1.5) -> lon from 0.5 to 1.5, lat from 0 to 0.1
    # dx = 1, dy = 0.1. Bearing = atan2(dx, dy) * 180/pi (relative to North)
    # Using Position(lat, lon):
    # Brunnel from (lat=0, lon=0.5) to (lat=0.1, lon=1.5)
    # Start (lon=0.5, lat=0). End (lon=1.5, lat=0.1) (Using geometry_utils convention for calculate_bearing)
    # Bearing = calculate_bearing( (0.5,0), (1.5,0.1) )
    # This is approx. 84.3 degrees. Difference from 90 is 5.7 deg.
    brunnel_coords = [Position(0, 0.5), Position(0.1, 1.5)]
    brunnel = MockBrunnel(BrunnelType.BRIDGE, brunnel_coords)
    assert brunnel.is_aligned_with_route(horizontal_route, tolerance_degrees=10) is True
    assert (
        brunnel.is_aligned_with_route(horizontal_route, tolerance_degrees=5) is False
    )  # Outside 5 deg tolerance


def test_is_aligned_with_route_short_brunnel_or_route():
    # Case where brunnel or route has < 2 points
    route_single_point = create_mock_route([Position(0, 0)])
    brunnel_coords = [Position(0, 0), Position(0, 1)]
    brunnel = MockBrunnel(BrunnelType.BRIDGE, brunnel_coords)
    assert (
        brunnel.is_aligned_with_route(route_single_point, 10) is False
    )  # Route too short

    brunnel_single_point = MockBrunnel(BrunnelType.BRIDGE, [Position(0, 0)])
    # horizontal_route is P(0,0), P(0,1), P(0,2)
    assert (
        brunnel_single_point.is_aligned_with_route(horizontal_route, 10) is False
    )  # Brunnel too short

    brunnel_no_points = MockBrunnel(BrunnelType.BRIDGE, [])
    assert brunnel_no_points.is_aligned_with_route(horizontal_route, 10) is False


def test_is_aligned_diagonal_route_and_brunnel():
    # Route P(0,0) to P(1,1) -> bearing 45 deg (NE)
    # Position(lat,lon) so (0,0) (1,1) (2,2) means lat=0,lon=0 to lat=1,lon=1
    # For calculate_bearing this is (lon=0,lat=0) to (lon=1,lat=1) -> NE, 45 deg
    diag_route = create_mock_route([Position(0, 0), Position(1, 1), Position(2, 2)])
    # Brunnel P(0.5,0.5) to P(1.5,1.5) -> also 45 deg
    brunnel_coords = [Position(0.5, 0.5), Position(1.5, 1.5)]
    brunnel = MockBrunnel(BrunnelType.BRIDGE, brunnel_coords)
    assert brunnel.is_aligned_with_route(diag_route, 10) is True

    # Brunnel P(0.5,0.5) to P(1.5,0.6) -> slightly off 45 deg
    # Start (lon=0.5, lat=0.5), End (lon=0.6, lat=1.5) for calculate_bearing
    # Using Position(lat,lon): Start(lat=0.5,lon=0.5), End(lat=1.5,lon=0.6)
    # calculate_bearing expects (lon,lat) points.
    # So, (0.5, 0.5) and (0.6, 1.5) for calculate_bearing for brunnel
    # Bearing for this is atan2(0.6-0.5, 1.5-0.5)*180/pi = atan2(0.1, 1.0)*180/pi = 5.71 deg
    # This is not what I intended.
    # Let's use points that give ~40 or ~50 deg for NE.
    # Route bearing is 45 deg.
    # To get brunnel bearing ~40 deg (relative to North, Eastward): needs dx slightly less than dy for (lon,lat) points
    # A brunnel from (lat=0.5,lon=0.5) to (lat=1.5,lon=1.4)
    # For calculate_bearing: (lon=0.5,lat=0.5) to (lon=1.4,lat=1.5)
    # Bearing = calculate_bearing( (0.5,0.5), (1.4,1.5) ) = atan2(1.4-0.5, 1.5-0.5)*180/pi = atan2(0.9, 1.0)*180/pi = 41.98 deg.
    # Difference from 45 is ~3.01 deg.
    brunnel_coords_slightly_off = [Position(0.5, 0.5), Position(1.5, 1.4)]
    brunnel_off = MockBrunnel(BrunnelType.BRIDGE, brunnel_coords_slightly_off)
    assert brunnel_off.is_aligned_with_route(diag_route, tolerance_degrees=5) is True
    assert brunnel_off.is_aligned_with_route(diag_route, tolerance_degrees=2) is False


# Helper function to create BrunnelWay for compound tests
def create_test_way(
    way_id: int,
    nodes: list[int],
    brunnel_type: BrunnelType = BrunnelType.BRIDGE,
    contained: bool = True,
    start_km: float = 0.0,
    end_km: float = 1.0,
    filter_reason: FilterReason = FilterReason.NONE,
) -> BrunnelWay:
    # Coords are not strictly needed for detect_adjacent_groups if node sharing is primary logic,
    # but good to have for completeness if any part of it uses geometry.
    # shares_node_with uses metadata['nodes']
    # detect_adjacent_groups filters by contained_in_route, route_span != None, filter_reason == NONE
    # and sorts by route_span.start_distance_km
    coords = [Position(0, 0), Position(1, 0)]  # Dummy coords
    metadata = {"id": way_id, "nodes": nodes, "tags": {}}
    way = BrunnelWay(
        coords=coords,
        metadata=metadata,
        brunnel_type=brunnel_type,
        contained_in_route=contained,
        filter_reason=filter_reason,
    )
    if contained and filter_reason == FilterReason.NONE:
        way.route_span = RouteSpan(start_km, end_km)
    return way


# Tests for CompoundBrunnelWay.detect_adjacent_groups


def test_detect_adjacent_groups_empty_list():
    assert CompoundBrunnelWay.detect_adjacent_groups([]) == []


def test_detect_adjacent_groups_no_groups():
    brunnels = [
        create_test_way(1, [10, 20], start_km=0, end_km=1),  # B1
        create_test_way(
            2, [30, 40], start_km=2, end_km=3
        ),  # B2 (no shared node with B1)
        create_test_way(3, [50, 60], start_km=4, end_km=5),  # B3
    ]
    assert CompoundBrunnelWay.detect_adjacent_groups(brunnels) == []


def test_detect_adjacent_groups_one_group_two_brunnels():
    brunnels = [
        create_test_way(1, [10, 20], start_km=0, end_km=1),  # B1
        create_test_way(
            2, [20, 30], start_km=1, end_km=2
        ),  # B2 (shares node 20 with B1)
        create_test_way(3, [40, 50], start_km=3, end_km=4),  # B3
    ]
    # Expected: brunnel at index 0 (B1) and brunnel at index 1 (B2) form a group
    expected_groups = [[0, 1]]
    assert CompoundBrunnelWay.detect_adjacent_groups(brunnels) == expected_groups


def test_detect_adjacent_groups_one_group_three_brunnels():
    brunnels = [
        create_test_way(1, [10, 20], start_km=0, end_km=1),  # B1
        create_test_way(2, [20, 30], start_km=1, end_km=2),  # B2
        create_test_way(3, [30, 40], start_km=2, end_km=3),  # B3
    ]
    expected_groups = [[0, 1, 2]]
    assert CompoundBrunnelWay.detect_adjacent_groups(brunnels) == expected_groups


def test_detect_adjacent_groups_two_separate_groups():
    brunnels = [
        create_test_way(1, [10, 20], start_km=0, end_km=1),  # G1-B1
        create_test_way(2, [20, 30], start_km=1, end_km=2),  # G1-B2
        create_test_way(3, [40, 50], start_km=3, end_km=4),  # Separator
        create_test_way(4, [60, 70], start_km=5, end_km=6),  # G2-B1
        create_test_way(5, [70, 80], start_km=6, end_km=7),  # G2-B2
    ]
    # Indices in the original list: B1=0, B2=1, B3=2, B4=3, B5=4
    expected_groups = [[0, 1], [3, 4]]
    assert CompoundBrunnelWay.detect_adjacent_groups(brunnels) == expected_groups


def test_detect_adjacent_groups_mixed_types_no_grouping_across_types():
    brunnels = [
        create_test_way(
            1, [10, 20], brunnel_type=BrunnelType.BRIDGE, start_km=0, end_km=1
        ),  # Bridge 1
        create_test_way(
            2, [20, 30], brunnel_type=BrunnelType.TUNNEL, start_km=1, end_km=2
        ),  # Tunnel 1 (shares node but different type)
        create_test_way(
            3, [30, 40], brunnel_type=BrunnelType.TUNNEL, start_km=2, end_km=3
        ),  # Tunnel 2
    ]
    # Expected: Tunnel 1 and Tunnel 2 form a group (indices 1, 2)
    expected_groups = [[1, 2]]
    assert CompoundBrunnelWay.detect_adjacent_groups(brunnels) == expected_groups


def test_detect_adjacent_groups_respects_filters_and_containment():
    brunnels = [
        create_test_way(
            1,
            [10, 20],
            start_km=0,
            end_km=1,
            contained=True,
            filter_reason=FilterReason.NONE,
        ),  # 0: Valid B1
        create_test_way(
            2,
            [20, 30],
            start_km=1,
            end_km=2,
            contained=False,
            filter_reason=FilterReason.NONE,
        ),  # 1: Not contained
        create_test_way(
            3,
            [30, 40],
            start_km=2,
            end_km=3,
            contained=True,
            filter_reason=FilterReason.RAILWAY,
        ),  # 2: Filtered out
        create_test_way(
            4,
            [40, 50],
            start_km=3,
            end_km=4,
            contained=True,
            filter_reason=FilterReason.NONE,
        ),  # 3: Valid B2 (no connection to B1)
        create_test_way(
            5,
            [50, 60],
            start_km=4,
            end_km=5,
            contained=True,
            filter_reason=FilterReason.NONE,
        ),  # 4: Valid B3 (connects to B2)
        create_test_way(
            6,
            [70, 80],
            start_km=6,
            end_km=7,
            contained=True,
            filter_reason=FilterReason.NONE,
            brunnel_type=BrunnelType.TUNNEL,
        ),  # 5: Valid T1
        create_test_way(
            7,
            [80, 90],
            start_km=7,
            end_km=8,
            contained=True,
            filter_reason=FilterReason.NONE,
            brunnel_type=BrunnelType.TUNNEL,
        ),  # 6: Valid T2 (connects to T1)
    ]
    # Expected: B2 and B3 form a group (indices 3, 4)
    # T1 and T2 form another group (indices 5, 6)
    # Note: indices are from the original list `brunnels`
    expected_groups = [[3, 4], [5, 6]]
    # Sort by first element of each group to ensure consistent order for comparison
    detected_groups = sorted(
        CompoundBrunnelWay.detect_adjacent_groups(brunnels), key=lambda x: x[0]
    )
    assert detected_groups == expected_groups


def test_detect_adjacent_groups_order_by_start_distance():
    # Brunnels not initially sorted by start_km to test sorting within detect_adjacent_groups
    brunnels = [
        create_test_way(
            1, [20, 30], start_km=1, end_km=2
        ),  # Index 0, B2 (connects to B1)
        create_test_way(2, [10, 20], start_km=0, end_km=1),  # Index 1, B1
        create_test_way(
            3, [30, 40], start_km=2, end_km=3
        ),  # Index 2, B3 (connects to B2)
    ]
    # After sorting by start_km: B1 (idx 1), B2 (idx 0), B3 (idx 2)
    # Group should be [original_idx_B1, original_idx_B2, original_idx_B3] -> [1, 0, 2]
    expected_groups = [[1, 0, 2]]
    assert CompoundBrunnelWay.detect_adjacent_groups(brunnels) == expected_groups


def test_detect_adjacent_groups_single_valid_brunnel():
    brunnels = [create_test_way(1, [10, 20])]
    assert CompoundBrunnelWay.detect_adjacent_groups(brunnels) == []


def test_detect_adjacent_groups_two_valid_brunnels_not_sharing_nodes():
    brunnels = [
        create_test_way(1, [10, 20], start_km=0, end_km=1),
        create_test_way(2, [30, 40], start_km=2, end_km=3),
    ]
    assert CompoundBrunnelWay.detect_adjacent_groups(brunnels) == []


def test_detect_adjacent_groups_no_nodes_metadata():
    # BrunnelWay.shares_node_with handles missing 'nodes' key
    way1 = create_test_way(1, [], start_km=0, end_km=1)  # No nodes in metadata
    way2 = create_test_way(2, [20, 30], start_km=1, end_km=2)
    brunnels = [way1, way2]
    assert CompoundBrunnelWay.detect_adjacent_groups(brunnels) == []

    way3 = create_test_way(3, [10, 20], start_km=0, end_km=1)
    way4 = create_test_way(4, [], start_km=1, end_km=2)  # No nodes in metadata
    brunnels2 = [way3, way4]
    assert CompoundBrunnelWay.detect_adjacent_groups(brunnels2) == []


def test_detect_adjacent_groups_node_sharing_logic_complex():
    # B1: [1,2] @ 0-1km
    # B2: [2,3] @ 1-2km (adj to B1)
    # B3: [4,5] @ 2-3km (not adj to B2)
    # B4: [5,6] @ 3-4km (adj to B3)
    # B5: [3,7] @ 4-5km (adj to B2, but B2 is already grouped with B1. B5 is later)
    brunnels = [
        create_test_way(1, [1, 2], start_km=0, end_km=1),  # idx 0
        create_test_way(2, [2, 3], start_km=1, end_km=2),  # idx 1
        create_test_way(3, [4, 5], start_km=2, end_km=3),  # idx 2
        create_test_way(4, [5, 6], start_km=3, end_km=4),  # idx 3
        create_test_way(5, [3, 7], start_km=4, end_km=5),  # idx 4
    ]
    # Expected: [[0,1], [2,3]]
    # B5 (idx 4) shares node 3 with B2 (idx 1).
    # Current algorithm:
    # Sort by start_km: [0,1,2,3,4] (already sorted)
    # Group by type: all BRIDGE
    # current_group = [0]
    # i=1 (brunnels[1]): prev=brunnels[0], curr=brunnels[1]. Share node 2. current_group = [0,1]
    # i=2 (brunnels[2]): prev=brunnels[1], curr=brunnels[2]. No shared node. Add [0,1] to adjacent_groups. current_group = [2]
    # i=3 (brunnels[3]): prev=brunnels[2], curr=brunnels[3]. Share node 5. current_group = [2,3]
    # i=4 (brunnels[4]): prev=brunnels[3], curr=brunnels[4]. No shared node. Add [2,3] to adjacent_groups. current_group = [4]
    # End loop. Last current_group [4] has len 1, not added.
    # Result: [[0,1], [2,3]]
    expected_groups = [[0, 1], [2, 3]]
    assert CompoundBrunnelWay.detect_adjacent_groups(brunnels) == expected_groups


# Tests for CompoundBrunnelWay.create_from_brunnels


def test_create_from_brunnels_no_compounds_formed():
    brunnels = [
        create_test_way(1, [10, 20], start_km=0, end_km=1),
        create_test_way(2, [30, 40], start_km=2, end_km=3),
    ]
    result = CompoundBrunnelWay.create_from_brunnels(brunnels)
    assert len(result) == 2
    assert all(isinstance(b, BrunnelWay) for b in result)
    assert not any(isinstance(b, CompoundBrunnelWay) for b in result)
    # Check original objects are returned
    assert result[0] is brunnels[0]
    assert result[1] is brunnels[1]


def test_create_from_brunnels_one_compound_formed():
    brunnels = [
        create_test_way(
            1, [10, 20], start_km=0, end_km=1, brunnel_type=BrunnelType.BRIDGE
        ),  # B1
        create_test_way(
            2, [20, 30], start_km=1, end_km=2, brunnel_type=BrunnelType.BRIDGE
        ),  # B2 (adj to B1)
        create_test_way(
            3, [40, 50], start_km=3, end_km=4, brunnel_type=BrunnelType.BRIDGE
        ),  # B3
    ]
    result = CompoundBrunnelWay.create_from_brunnels(brunnels)
    assert len(result) == 2  # One compound + B3

    compound_brunnel = next(
        (b for b in result if isinstance(b, CompoundBrunnelWay)), None
    )
    assert compound_brunnel is not None
    assert len(compound_brunnel.components) == 2
    assert compound_brunnel.components[0].metadata["id"] == 1  # B1
    assert compound_brunnel.components[1].metadata["id"] == 2  # B2
    assert compound_brunnel.brunnel_type == BrunnelType.BRIDGE
    assert compound_brunnel.contained_in_route is True  # Set by create_from_brunnels
    assert (
        compound_brunnel.filter_reason == FilterReason.NONE
    )  # Set by create_from_brunnels

    # Check route span of compound
    assert compound_brunnel.route_span is not None
    assert compound_brunnel.route_span.start_distance_km == pytest.approx(
        0.0
    )  # min of B1, B2 start_km
    assert compound_brunnel.route_span.end_distance_km == pytest.approx(
        2.0
    )  # max of B1, B2 end_km

    remaining_brunnel = next(
        (
            b
            for b in result
            if isinstance(b, BrunnelWay) and not isinstance(b, CompoundBrunnelWay)
        ),
        None,
    )
    assert remaining_brunnel is not None
    assert remaining_brunnel.metadata["id"] == 3  # B3


def test_create_from_brunnels_all_form_one_compound():
    brunnels = [
        create_test_way(1, [10, 20], start_km=0, end_km=1),
        create_test_way(2, [20, 30], start_km=1, end_km=2),
        create_test_way(3, [30, 40], start_km=2, end_km=3),
    ]
    result = CompoundBrunnelWay.create_from_brunnels(brunnels)
    assert len(result) == 1
    assert isinstance(result[0], CompoundBrunnelWay)
    compound_brunnel = result[0]
    assert len(compound_brunnel.components) == 3
    assert compound_brunnel.route_span is not None
    assert compound_brunnel.route_span.start_distance_km == pytest.approx(0.0)
    assert compound_brunnel.route_span.end_distance_km == pytest.approx(3.0)


def test_create_from_brunnels_multiple_compounds_and_individuals():
    brunnels = [
        create_test_way(
            1, [10, 20], start_km=0, end_km=1, brunnel_type=BrunnelType.BRIDGE
        ),  # C1-B1
        create_test_way(
            2, [20, 30], start_km=1, end_km=2, brunnel_type=BrunnelType.BRIDGE
        ),  # C1-B2
        create_test_way(
            3, [100, 110], start_km=2.5, end_km=3, brunnel_type=BrunnelType.BRIDGE
        ),  # Individual Bridge
        create_test_way(
            4, [40, 50], start_km=3, end_km=4, brunnel_type=BrunnelType.TUNNEL
        ),  # C2-T1
        create_test_way(
            5, [50, 60], start_km=4, end_km=5, brunnel_type=BrunnelType.TUNNEL
        ),  # C2-T2
        create_test_way(
            6, [60, 70], start_km=5, end_km=6, brunnel_type=BrunnelType.TUNNEL
        ),  # C2-T3
        create_test_way(
            7, [200, 210], start_km=7, end_km=8, brunnel_type=BrunnelType.BRIDGE
        ),  # Individual Bridge 2
    ]
    result = CompoundBrunnelWay.create_from_brunnels(brunnels)
    assert len(result) == 4  # C1, Individual B, C2, Individual B2

    compound_brunnels = [b for b in result if isinstance(b, CompoundBrunnelWay)]
    individual_brunnels = [
        b
        for b in result
        if isinstance(b, BrunnelWay) and not isinstance(b, CompoundBrunnelWay)
    ]

    assert len(compound_brunnels) == 2
    assert len(individual_brunnels) == 2

    c1 = next(c for c in compound_brunnels if c.brunnel_type == BrunnelType.BRIDGE)
    c2 = next(c for c in compound_brunnels if c.brunnel_type == BrunnelType.TUNNEL)

    assert len(c1.components) == 2
    assert c1.components[0].metadata["id"] == 1
    assert c1.route_span is not None
    assert c1.route_span.start_distance_km == pytest.approx(0.0)
    assert c1.route_span.end_distance_km == pytest.approx(2.0)

    assert len(c2.components) == 3
    assert c2.components[0].metadata["id"] == 4
    assert c2.route_span is not None
    assert c2.route_span.start_distance_km == pytest.approx(3.0)
    assert c2.route_span.end_distance_km == pytest.approx(6.0)

    assert individual_brunnels[0].metadata["id"] == 3
    assert individual_brunnels[1].metadata["id"] == 7


def test_create_from_brunnels_empty_input():
    assert CompoundBrunnelWay.create_from_brunnels([]) == []


def test_create_from_brunnels_handles_detection_failure_gracefully():
    # If detect_adjacent_groups somehow returns invalid indices or empty groups,
    # create_from_brunnels should ideally not crash.
    # This is hard to test without mocking detect_adjacent_groups itself.
    # However, if detect_adjacent_groups returns [] (no groups), it's covered by no_compounds_formed.
    # If a group has < 2 indices, it's skipped in create_from_brunnels.

    # Scenario: Group detected, but one component is problematic (e.g., missing route_span after filtering)
    # The create_test_way helper ensures route_span is None if not valid for grouping.
    # detect_adjacent_groups should not group items without route_span.
    brunnels = [
        create_test_way(1, [10, 20], start_km=0, end_km=1),
        create_test_way(
            2, [20, 30], start_km=1, end_km=2, contained=False
        ),  # No route_span because not contained
    ]
    result = CompoundBrunnelWay.create_from_brunnels(brunnels)
    # Should not form a compound because way 2 is filtered out by detect_adjacent_groups
    assert len(result) == 2
    assert result[0].metadata["id"] == 1
    assert result[1].metadata["id"] == 2
    assert not any(isinstance(b, CompoundBrunnelWay) for b in result)


def test_create_from_brunnels_preserves_original_list_order_for_non_compounded():
    # Test that individual brunnels that are not part of any compound maintain their relative order.
    brunnels = [
        create_test_way(10, [1, 2], start_km=0, end_km=1),  # Individual A
        create_test_way(1, [10, 20], start_km=1, end_km=2),  # Compound P1
        create_test_way(2, [20, 30], start_km=2, end_km=3),  # Compound P2
        create_test_way(20, [4, 5], start_km=3, end_km=4),  # Individual B
        create_test_way(3, [40, 50], start_km=4, end_km=5),  # Compound Q1
        create_test_way(4, [50, 60], start_km=5, end_km=6),  # Compound Q2
        create_test_way(30, [7, 8], start_km=6, end_km=7),  # Individual C
    ]
    result = CompoundBrunnelWay.create_from_brunnels(brunnels)

    # Expected: CompoundP, CompoundQ, Indiv A, Indiv B, Indiv C (order of compounds then individuals)
    # The current implementation adds compounds first, then remaining individuals.
    # So, the order of individuals relative to each other should be preserved.

    assert len(result) == 5  # CompoundP, CompoundQ, IndivA, IndivB, IndivC

    compound_P = result[0]
    compound_Q = result[1]
    indiv_A = result[2]
    indiv_B = result[3]
    indiv_C = result[4]

    assert isinstance(compound_P, CompoundBrunnelWay)
    assert compound_P.components[0].metadata["id"] == 1

    assert isinstance(compound_Q, CompoundBrunnelWay)
    assert compound_Q.components[0].metadata["id"] == 3

    assert indiv_A.metadata["id"] == 10
    assert indiv_B.metadata["id"] == 20
    assert indiv_C.metadata["id"] == 30
