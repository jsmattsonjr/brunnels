import unittest
from shapely.geometry import LineString, Point
from src.brunnels.brunnel import Brunnel, BrunnelType, RouteSpan
from src.brunnels.route import Route
from src.brunnels.geometry import Position

class TestBrunnel(unittest.TestCase):
    def _create_mock_route(self, route_coords_tuples):
        """Helper to create a Route object from a list of (lat, lon) tuples."""
        # Position expects (latitude, longitude)
        positions = [Position(lat, lon) for lat, lon in route_coords_tuples]
        mock_route = Route(positions)
        # Shapely LineString expects (x, y) which we map to (longitude, latitude)
        mock_route.linestring = LineString([(p.longitude, p.latitude) for p in positions])
        return mock_route

    def _create_mock_brunnel(self, brunnel_coords_tuples, brunnel_type=BrunnelType.BRIDGE):
        """Helper to create a Brunnel object from a list of (lat, lon) tuples."""
        # Position expects (latitude, longitude)
        positions = [Position(lat, lon) for lat, lon in brunnel_coords_tuples]
        brunnel = Brunnel(positions, {}, brunnel_type)
        # Shapely LineString expects (x, y) which we map to (longitude, latitude)
        brunnel.linestring = LineString([(p.longitude, p.latitude) for p in positions])
        return brunnel

    def test_calculate_route_span_example(self):
        """Test the example case provided in the problem description."""
        # Route: Line from (lat=0,lon=0) to (lat=0,lon=100.0) -> length 100.0m on x-axis (lon)
        # Scaled down by 100x to avoid antimeridian check with large lon values.
        mock_route = self._create_mock_route([(0,0), (0,100.0)])

        # Original example values scaled down by 100x:
        # D1 = 50.00m. Brunnel length = 1.00m (used for substring window if it were a fixed input).
        # Substring spans [49.00m, 51.00m] on route.
        # Endpoint B projects to D2_substring = 0.80m along this substring.
        # D2 = 49.00 + 0.80 = 49.80m. Route span = (49.80m, 50.00m).

        # To achieve this with current code (which uses geometric brunnel length):
        # Brunnel from A to B. A projects to D1=50.00. B projects to D2=49.80 (after calculation).
        # Let A be (lat=0.01, lon=50.00). Let B be (lat=0.01, lon=49.80). (Using small lat to avoid being on the line itself)
        # Geometric length of this brunnel is sqrt((50.00-49.80)^2 + (0.01-0.01)^2) = 0.20.
        # So, self.linestring.length will be 0.20.
        # D1 = 50.00 (projection of (lon=50.00, lat=0.01) onto x-axis route)
        # brunnel_length_calc = 0.20.
        # substring_start = max(0, 50.00 - 0.20) = 49.80.
        # substring_end = min(100.0, 50.00 + 0.20) = 50.20.
        # route_substring_geom is LineString([(49.80,0), (50.20,0)]) on x-axis. Length 0.40.
        # Endpoint B is (lat=0.01, lon=49.80). Shapely point is (49.80, 0.01).
        # d2_substring = route_substring_geom.project(Point(49.80, 0.01)) = 0 (projects to start of substring).
        # d2 = substring_start + d2_substring = 49.80 + 0 = 49.80.
        # Span = (min(50.00,49.80), max(50.00,49.80)) = (49.80, 50.00). This matches the example's span logic.

        brunnel_A_pos = (0.01, 50.00) # lat, lon for Position object
        brunnel_B_pos = (0.01, 49.80) # lat, lon for Position object
        mock_brunnel_ex = self._create_mock_brunnel([brunnel_A_pos, brunnel_B_pos])
        # Shapely linestring will be [(50.00, 0.01), (49.80, 0.01)] -> length 0.20.
        self.assertAlmostEqual(mock_brunnel_ex.linestring.length, 0.20, places=5)

        mock_brunnel_ex.calculate_route_span(mock_route)
        self.assertIsNotNone(mock_brunnel_ex.route_span)
        self.assertAlmostEqual(mock_brunnel_ex.route_span.start_distance, 49.80, places=5)
        self.assertAlmostEqual(mock_brunnel_ex.route_span.end_distance, 50.00, places=5)

        # Test with a brunnel of geometric length 1.00 (scaled from 100m) to see different results:
        # Brunnel from (lat=0.01,lon=50.00) to (lat=0.01,lon=49.00). Length 1.00.
        # D1 = 50.00. L_geom=1.00. Substring_calc=[50.00-1.00, 50.00+1.00] = [49.00,51.00].
        # Endpoint B is (lat=0.01,lon=49.00). Shapely point (49.00,0.01).
        # d2_substring for (49.00,0.01) on substring LineString((49.00,0),(51.00,0)) is 0.
        # d2_calc = 49.00+0=49.00. Span (49.00,50.00).
        mock_brunnel_len1 = self._create_mock_brunnel([(0.01,50.00), (0.01,49.00)])
        self.assertAlmostEqual(mock_brunnel_len1.linestring.length, 1.00, places=5)
        mock_brunnel_len1.calculate_route_span(mock_route)
        self.assertIsNotNone(mock_brunnel_len1.route_span)
        self.assertAlmostEqual(mock_brunnel_len1.route_span.start_distance, 49.00, places=5)
        self.assertAlmostEqual(mock_brunnel_len1.route_span.end_distance, 50.00, places=5)


    def test_calculate_route_span_brunnel_at_route_start(self):
        """Test brunnel starting at the beginning of the route."""
        mock_route = self._create_mock_route([(0,0), (0,100)]) # Route lat=0, lon from 0 to 100. Length 100
        # Brunnel from (lat=1,lon=0) to (lat=1,lon=10). Length 10.
        mock_brunnel = self._create_mock_brunnel([(1,0), (1,10)])

        mock_brunnel.calculate_route_span(mock_route)
        self.assertIsNotNone(mock_brunnel.route_span)
        self.assertAlmostEqual(mock_brunnel.route_span.start_distance, 0, places=5)
        self.assertAlmostEqual(mock_brunnel.route_span.end_distance, 10, places=5)

    def test_calculate_route_span_brunnel_at_route_end(self):
        """Test brunnel ending at the end of the route."""
        mock_route = self._create_mock_route([(0,0), (0,100)]) # Route lat=0, lon from 0 to 100. Length 100
        # Brunnel from (lat=1,lon=90) to (lat=1,lon=100). Length 10.
        mock_brunnel = self._create_mock_brunnel([(1,90), (1,100)])

        mock_brunnel.calculate_route_span(mock_route)
        self.assertIsNotNone(mock_brunnel.route_span)
        self.assertAlmostEqual(mock_brunnel.route_span.start_distance, 90, places=5)
        self.assertAlmostEqual(mock_brunnel.route_span.end_distance, 100, places=5)

    def test_calculate_route_span_brunnel_longer_than_route(self):
        """Test brunnel that is geometrically longer than the route."""
        mock_route = self._create_mock_route([(0,0), (0,50)]) # Route lat=0, lon from 0 to 50. Length 50
        # Brunnel from (lat=1,lon=-10) to (lat=1,lon=60). Length 70.
        mock_brunnel = self._create_mock_brunnel([(1,-10), (1,60)])
        self.assertAlmostEqual(mock_brunnel.linestring.length, 70.0, places=5)

        mock_brunnel.calculate_route_span(mock_route)
        self.assertIsNotNone(mock_brunnel.route_span)
        self.assertAlmostEqual(mock_brunnel.route_span.start_distance, 0, places=5)
        self.assertAlmostEqual(mock_brunnel.route_span.end_distance, 50, places=5)

    def test_calculate_route_span_endpoints_project_to_same_point(self):
        """Test brunnel whose endpoints project to the same point on the route (e.g., perpendicular brunnel)."""
        mock_route = self._create_mock_route([(0,0), (0,100)]) # Route lat=0, lon from 0 to 100. Length 100
        # Brunnel from (lat=1,lon=50) to (lat=11,lon=50). Length 10. Perpendicular.
        # Shapely points: (50,1) and (50,11)
        mock_brunnel = self._create_mock_brunnel([(1,50), (11,50)])
        self.assertAlmostEqual(mock_brunnel.linestring.length, 10.0, places=5)

        mock_brunnel.calculate_route_span(mock_route)
        self.assertIsNotNone(mock_brunnel.route_span)
        self.assertAlmostEqual(mock_brunnel.route_span.start_distance, 50, places=5)
        self.assertAlmostEqual(mock_brunnel.route_span.end_distance, 50, places=5)

    def test_calculate_route_span_brunnel_endpoints_beyond_route_ends(self):
        """Test brunnel whose endpoints are beyond the ends of the route."""
        # Route from (lat=0,lon=10) to (lat=0,lon=20), length 10
        mock_route = self._create_mock_route([(0,10), (0,20)])
        # Brunnel from (lat=1,lon=0) to (lat=1,lon=30). Length 30.
        mock_brunnel = self._create_mock_brunnel([(1,0), (1,30)])
        self.assertAlmostEqual(mock_brunnel.linestring.length, 30.0, places=5)

        mock_brunnel.calculate_route_span(mock_route)
        self.assertIsNotNone(mock_brunnel.route_span)
        self.assertAlmostEqual(mock_brunnel.route_span.start_distance, 0, places=5)
        self.assertAlmostEqual(mock_brunnel.route_span.end_distance, 10, places=5)

    def test_calculate_route_span_short_route_long_brunnel_causes_negative_substring_raw_start(self):
        """ Test case where D1 - brunnel_length is negative, but max(0,...) handles it. """
        mock_route = self._create_mock_route([(0,0), (0,10)]) # Route length 10 (lon from 0 to 10)
        # Brunnel from (lat=1,lon=1) to (lat=1,lon=101). Length 100.
        mock_brunnel = self._create_mock_brunnel([(1,1), (1,101)])
        self.assertAlmostEqual(mock_brunnel.linestring.length, 100.0, places=5)

        mock_brunnel.calculate_route_span(mock_route)
        self.assertIsNotNone(mock_brunnel.route_span)
        self.assertAlmostEqual(mock_brunnel.route_span.start_distance, 1, places=5)
        self.assertAlmostEqual(mock_brunnel.route_span.end_distance, 10, places=5)

    def test_calculate_route_span_substring_start_greater_than_end_fallback(self):
        """ Test where substring_start > substring_end, or other empty/invalid substring cases. """
        # Test the `substring_start == substring_end` path leading to d2 = substring_start
        # Route: very short, e.g., (lat=0,lon=0) to (lat=0, lon=0.0000001)
        mock_route = self._create_mock_route([(0,0), (0,0.0000001)])
        # Brunnel: (lat=1,lon=0) to (lat=1,lon=1)
        mock_brunnel = self._create_mock_brunnel([(1,0), (1,1)])

        mock_brunnel.calculate_route_span(mock_route)
        self.assertIsNotNone(mock_brunnel.route_span)
        self.assertAlmostEqual(mock_brunnel.route_span.start_distance, 0, places=5)
        self.assertAlmostEqual(mock_brunnel.route_span.end_distance, 0, places=5)

        # Test the `route_substring_geom.is_empty` or zero length fallback
        # Route made of two identical points: (lat=0,lon=5) to (lat=0,lon=5). Length 0.
        mock_route_zero_len = self._create_mock_route([(0,5), (0,5)])
        self.assertEqual(mock_route_zero_len.linestring.length, 0)
        # Brunnel: (lat=1,lon=5) to (lat=1,lon=6)
        mock_brunnel_on_zero_route = self._create_mock_brunnel([(1,5),(1,6)])

        mock_brunnel_on_zero_route.calculate_route_span(mock_route_zero_len)
        self.assertIsNotNone(mock_brunnel_on_zero_route.route_span)
        self.assertAlmostEqual(mock_brunnel_on_zero_route.route_span.start_distance, 0, places=5)
        self.assertAlmostEqual(mock_brunnel_on_zero_route.route_span.end_distance, 0, places=5)

if __name__ == '__main__':
    unittest.main()
