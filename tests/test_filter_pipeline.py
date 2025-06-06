import unittest
from typing import List
from dataclasses import dataclass, field

from src.brunnels.brunnel import FilterReason, BrunnelType
from src.brunnels.brunnel_way import BrunnelWay
from src.brunnels.filter_pipeline import FilterPipeline

# Mock BrunnelWay for testing
@dataclass
class MockBrunnelWay:
    name: str
    filter_reason: FilterReason = FilterReason.NONE
    brunnel_type: BrunnelType = BrunnelType.BRIDGE # Default type
    coords: List = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    contained_in_route: bool = False

    # Add a dummy get_id method to satisfy BrunnelWay's interface if needed by filters
    def get_id(self) -> str:
        return self.name

class TestFilterPipeline(unittest.TestCase):

    def test_add_filter(self):
        pipeline = FilterPipeline()
        self.assertEqual(len(pipeline.filters), 0)

        def dummy_filter(_: MockBrunnelWay) -> FilterReason:
            return FilterReason.NONE

        pipeline.add_filter(dummy_filter)
        self.assertEqual(len(pipeline.filters), 1)
        self.assertIs(pipeline.filters[0], dummy_filter)

        pipeline.add_filter(dummy_filter)
        self.assertEqual(len(pipeline.filters), 2)

    def test_apply_no_filters(self):
        pipeline = FilterPipeline()
        brunnels = [MockBrunnelWay("b1")]
        processed_brunnels = pipeline.apply(brunnels)
        self.assertEqual(len(processed_brunnels), 1)
        self.assertEqual(processed_brunnels[0].filter_reason, FilterReason.NONE)

    def test_apply_filter_returns_none(self):
        pipeline = FilterPipeline()
        def filter_none(_: MockBrunnelWay) -> FilterReason:
            return FilterReason.NONE

        pipeline.add_filter(filter_none)
        brunnels = [MockBrunnelWay("b1")]
        processed_brunnels = pipeline.apply(brunnels)
        self.assertEqual(processed_brunnels[0].filter_reason, FilterReason.NONE)

    def test_apply_filter_returns_reason(self):
        pipeline = FilterPipeline()
        reason_to_set = FilterReason.WATERWAY
        def filter_set_reason(_: MockBrunnelWay) -> FilterReason:
            return reason_to_set

        pipeline.add_filter(filter_set_reason)
        brunnels = [MockBrunnelWay("b1"), MockBrunnelWay("b2")]
        processed_brunnels = pipeline.apply(brunnels)

        self.assertEqual(processed_brunnels[0].filter_reason, reason_to_set)
        self.assertEqual(processed_brunnels[1].filter_reason, reason_to_set)

    def test_apply_multiple_filters_first_triggers(self):
        pipeline = FilterPipeline()
        reason1 = FilterReason.RAILWAY
        reason2 = FilterReason.BICYCLE_NO

        def filter1(b: MockBrunnelWay) -> FilterReason:
            if b.name == "b1":
                return reason1
            return FilterReason.NONE

        def filter2(b: MockBrunnelWay) -> FilterReason:
            # This filter should not be reached for b1 if filter1 triggers
            if b.name == "b1":
                return reason2
            if b.name == "b2":
                return reason2
            return FilterReason.NONE

        pipeline.add_filter(filter1).add_filter(filter2)
        brunnels = [MockBrunnelWay("b1"), MockBrunnelWay("b2"), MockBrunnelWay("b3")]
        processed_brunnels = pipeline.apply(brunnels)

        self.assertEqual(processed_brunnels[0].name, "b1")
        self.assertEqual(processed_brunnels[0].filter_reason, reason1) # Filter1 sets reason

        self.assertEqual(processed_brunnels[1].name, "b2")
        self.assertEqual(processed_brunnels[1].filter_reason, reason2) # Filter1 is NONE, Filter2 sets reason

        self.assertEqual(processed_brunnels[2].name, "b3")
        self.assertEqual(processed_brunnels[2].filter_reason, FilterReason.NONE) # Neither filter triggers

    def test_apply_filter_chaining(self):
        pipeline = FilterPipeline()
        reason = FilterReason.POLYGON

        def filter_poly(_: MockBrunnelWay) -> FilterReason:
            return reason

        pipeline.add_filter(filter_poly).add_filter(filter_poly) # Add same filter twice (not typical, but tests chaining)
        self.assertEqual(len(pipeline.filters), 2)

        brunnels = [MockBrunnelWay("b1")]
        processed_brunnels = pipeline.apply(brunnels)
        self.assertEqual(processed_brunnels[0].filter_reason, reason)


if __name__ == '__main__':
    unittest.main()
