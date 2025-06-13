import unittest
from typing import Optional

from src.brunnels.brunnel import Brunnel, RouteSpan, BrunnelType
from src.brunnels.geometry import Position # Assuming Position might be needed for Brunnel creation, though not strictly for these tests.

class TestBrunnelOverlapsWith(unittest.TestCase):

    def _create_brunnel_with_span(self, start: Optional[float], end: Optional[float]) -> Brunnel:
        """Helper method to create a Brunnel instance with a specific route_span."""
        # Coords and metadata are minimal for these tests as they don't affect overlap logic.
        brunnel = Brunnel(
            coords=[],  # Minimal coords
            metadata={}, # Minimal metadata
            brunnel_type=BrunnelType.BRIDGE # Default type
        )
        if start is not None and end is not None:
            brunnel.route_span = RouteSpan(start_distance=start, end_distance=end)
        else:
            brunnel.route_span = None
        return brunnel

    def test_both_spans_valid_and_overlapping_various_cases(self):
        # b1_start=10, b1_end=20, b2_start=15, b2_end=25 (direct overlap) -> True
        b1 = self._create_brunnel_with_span(10, 20)
        b2 = self._create_brunnel_with_span(15, 25)
        self.assertTrue(b1.overlaps_with(b2), "Direct overlap failed")
        self.assertTrue(b2.overlaps_with(b1), "Direct overlap (reversed) failed")

        # b1_start=10, b1_end=20, b2_start=5, b2_end=15 (overlap at start) -> True
        b1 = self._create_brunnel_with_span(10, 20)
        b2 = self._create_brunnel_with_span(5, 15)
        self.assertTrue(b1.overlaps_with(b2), "Overlap at start failed")
        self.assertTrue(b2.overlaps_with(b1), "Overlap at start (reversed) failed")

        # b1_start=10, b1_end=20, b2_start=10, b2_end=20 (exact same span) -> True
        b1 = self._create_brunnel_with_span(10, 20)
        b2 = self._create_brunnel_with_span(10, 20)
        self.assertTrue(b1.overlaps_with(b2), "Exact same span failed")
        self.assertTrue(b2.overlaps_with(b1), "Exact same span (reversed) failed")

        # b1_start=10, b1_end=20, b2_start=12, b2_end=18 (b2 contained in b1) -> True
        b1 = self._create_brunnel_with_span(10, 20)
        b2 = self._create_brunnel_with_span(12, 18)
        self.assertTrue(b1.overlaps_with(b2), "b2 contained in b1 failed")
        self.assertTrue(b2.overlaps_with(b1), "b2 contained in b1 (reversed) failed")

        # b1_start=12, b1_end=18, b2_start=10, b2_end=20 (b1 contained in b2) -> True
        b1 = self._create_brunnel_with_span(12, 18)
        b2 = self._create_brunnel_with_span(10, 20)
        self.assertTrue(b1.overlaps_with(b2), "b1 contained in b2 failed")
        self.assertTrue(b2.overlaps_with(b1), "b1 contained in b2 (reversed) failed")

    def test_both_spans_valid_and_not_overlapping_various_cases(self):
        # b1_start=10, b1_end=20, b2_start=25, b2_end=30 (b2 after b1) -> False
        b1 = self._create_brunnel_with_span(10, 20)
        b2 = self._create_brunnel_with_span(25, 30)
        self.assertFalse(b1.overlaps_with(b2), "b2 after b1 failed")
        self.assertFalse(b2.overlaps_with(b1), "b2 after b1 (reversed) failed")

        # b1_start=25, b1_end=30, b2_start=10, b2_end=20 (b2 before b1) -> False
        b1 = self._create_brunnel_with_span(25, 30)
        b2 = self._create_brunnel_with_span(10, 20)
        self.assertFalse(b1.overlaps_with(b2), "b2 before b1 failed")
        self.assertFalse(b2.overlaps_with(b1), "b2 before b1 (reversed) failed")

    def test_spans_touching_at_endpoints(self):
        # b1_start=10, b1_end=20, b2_start=20, b2_end=30 (touching, b2 starts where b1 ends) -> True
        b1 = self._create_brunnel_with_span(10, 20)
        b2 = self._create_brunnel_with_span(20, 30)
        self.assertTrue(b1.overlaps_with(b2), "Touching (b2 starts where b1 ends) failed")
        self.assertTrue(b2.overlaps_with(b1), "Touching (b2 starts where b1 ends, reversed) failed")

        # b1_start=20, b1_end=30, b2_start=10, b2_end=20 (touching, b1 starts where b2 ends) -> True
        b1 = self._create_brunnel_with_span(20, 30)
        b2 = self._create_brunnel_with_span(10, 20)
        self.assertTrue(b1.overlaps_with(b2), "Touching (b1 starts where b2 ends) failed")
        self.assertTrue(b2.overlaps_with(b1), "Touching (b1 starts where b2 ends, reversed) failed")

    def test_one_or_both_spans_are_none(self):
        b_valid = self._create_brunnel_with_span(10, 20)
        b_none = self._create_brunnel_with_span(None, None)

        # b1_span=valid, b2_span=None -> False
        self.assertFalse(b_valid.overlaps_with(b_none), "Valid with None span failed")

        # b1_span=None, b2_span=valid -> False
        self.assertFalse(b_none.overlaps_with(b_valid), "None with Valid span failed")

        # b1_span=None, b2_span=None -> False
        b_none2 = self._create_brunnel_with_span(None, None)
        self.assertFalse(b_none.overlaps_with(b_none2), "None with None span failed")

if __name__ == '__main__':
    unittest.main()
