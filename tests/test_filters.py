# tests/test_filters.py
import unittest
from dataclasses import dataclass, field
from typing import List, Dict, Any

from src.brunnels.brunnel import FilterReason, BrunnelType
# Need a mock BrunnelWay that can be instantiated for tests
@dataclass
class MockBrunnelWay:
    metadata: Dict[str, Any]
    # Add other fields that BrunnelWay expects if filter functions use them.
    # For these specific filters, only metadata (and metadata.nodes) is used.
    # The real BrunnelWay constructor would also need coords, brunnel_type etc.
    # We are testing filter functions which expect a BrunnelWay-like object.
    coords: List[Any] = field(default_factory=list) # Add dummy coords
    brunnel_type: BrunnelType = BrunnelType.BRIDGE # Add dummy type
    filter_reason: FilterReason = FilterReason.NONE # To be updated by pipeline

    # Add dummy get_id and other methods if filter functions ever needed them
    def get_id(self) -> str:
        return str(self.metadata.get("id", "unknown"))


# Now import the actual filter functions and pipeline creator
from src.brunnels.filters import (
    check_polygon_filter,
    check_bicycle_no_filter,
    check_waterway_filter,
    check_railway_filter,
    create_standard_brunnel_filter_pipeline
)
from src.brunnels.filter_pipeline import FilterPipeline

class TestBrunnelFilters(unittest.TestCase):

    def test_check_polygon_filter_is_polygon_filter_out(self):
        brunnel = MockBrunnelWay(metadata={"nodes": [1, 2, 3, 1]})
        self.assertEqual(check_polygon_filter(brunnel, keep_polygons=False), FilterReason.POLYGON)

    def test_check_polygon_filter_is_polygon_keep_polygons(self):
        brunnel = MockBrunnelWay(metadata={"nodes": [1, 2, 3, 1]})
        self.assertEqual(check_polygon_filter(brunnel, keep_polygons=True), FilterReason.NONE)

    def test_check_polygon_filter_not_polygon(self):
        brunnel = MockBrunnelWay(metadata={"nodes": [1, 2, 3, 4]})
        self.assertEqual(check_polygon_filter(brunnel, keep_polygons=False), FilterReason.NONE)

    def test_check_bicycle_no_filter_is_no(self):
        brunnel = MockBrunnelWay(metadata={"tags": {"bicycle": "no"}})
        self.assertEqual(check_bicycle_no_filter(brunnel), FilterReason.BICYCLE_NO)

    def test_check_bicycle_no_filter_is_yes(self):
        brunnel = MockBrunnelWay(metadata={"tags": {"bicycle": "yes"}})
        self.assertEqual(check_bicycle_no_filter(brunnel), FilterReason.NONE)

    def test_check_bicycle_no_filter_no_tag(self):
        brunnel = MockBrunnelWay(metadata={"tags": {}})
        self.assertEqual(check_bicycle_no_filter(brunnel), FilterReason.NONE)

    def test_check_waterway_filter_is_waterway(self):
        brunnel = MockBrunnelWay(metadata={"tags": {"waterway": "river"}})
        self.assertEqual(check_waterway_filter(brunnel), FilterReason.WATERWAY)

    def test_check_waterway_filter_is_waterway_bicycle_yes_override(self):
        brunnel = MockBrunnelWay(metadata={"tags": {"waterway": "river", "bicycle": "yes"}})
        self.assertEqual(check_waterway_filter(brunnel), FilterReason.NONE)

    def test_check_waterway_filter_is_waterway_cycleway_override(self):
        brunnel = MockBrunnelWay(metadata={"tags": {"waterway": "river", "highway": "cycleway"}})
        self.assertEqual(check_waterway_filter(brunnel), FilterReason.NONE)

    def test_check_waterway_filter_is_waterway_bicycle_no_no_override(self):
        brunnel = MockBrunnelWay(metadata={"tags": {"waterway": "river", "bicycle": "no"}})
        self.assertEqual(check_waterway_filter(brunnel), FilterReason.WATERWAY)


    def test_check_railway_filter_is_railway(self):
        brunnel = MockBrunnelWay(metadata={"tags": {"railway": "rail"}})
        self.assertEqual(check_railway_filter(brunnel), FilterReason.RAILWAY)

    def test_check_railway_filter_is_railway_abandoned(self):
        brunnel = MockBrunnelWay(metadata={"tags": {"railway": "abandoned"}})
        self.assertEqual(check_railway_filter(brunnel), FilterReason.NONE)

    def test_check_railway_filter_is_railway_bicycle_yes_override(self):
        brunnel = MockBrunnelWay(metadata={"tags": {"railway": "rail", "bicycle": "yes"}})
        self.assertEqual(check_railway_filter(brunnel), FilterReason.NONE)

    def test_check_railway_filter_is_railway_cycleway_override(self):
        brunnel = MockBrunnelWay(metadata={"tags": {"railway": "rail", "highway": "cycleway"}})
        self.assertEqual(check_railway_filter(brunnel), FilterReason.NONE)

class TestStandardBrunnelFilterPipeline(unittest.TestCase):

    def apply_pipeline_to_mock(self, metadata: Dict[str, Any], keep_polygons: bool = False, enable_tag_filtering: bool = True) -> FilterReason:
        # The actual BrunnelWay constructor is more complex.
        # For from_overpass_data, it creates a temp BrunnelWay.
        # We need to ensure our mock can be used similarly by the pipeline.
        # The pipeline expects BrunnelWay objects.
        # The filter functions expect an object with .metadata.

        # Let's use the MockBrunnelWay here for consistency with TestBrunnelFilters
        mock_brunnel = MockBrunnelWay(metadata=metadata)

        pipeline = create_standard_brunnel_filter_pipeline(keep_polygons, enable_tag_filtering)
        pipeline.apply([mock_brunnel]) # apply modifies mock_brunnel.filter_reason
        return mock_brunnel.filter_reason

    def test_pipeline_no_tag_filtering(self):
        reason = self.apply_pipeline_to_mock(metadata={"tags": {"bicycle": "no"}}, enable_tag_filtering=False)
        self.assertEqual(reason, FilterReason.NONE)

    def test_pipeline_polygon_filtered(self):
        reason = self.apply_pipeline_to_mock(metadata={"nodes": [1,2,1]}, keep_polygons=False)
        self.assertEqual(reason, FilterReason.POLYGON)

    def test_pipeline_polygon_kept(self):
        reason = self.apply_pipeline_to_mock(metadata={"nodes": [1,2,1]}, keep_polygons=True)
        self.assertEqual(reason, FilterReason.NONE)

    def test_pipeline_bicycle_no_highest_priority(self):
        # bicycle=no, but also a polygon. bicycle=no should win if polygon is checked first.
        # Order in create_standard_brunnel_filter_pipeline: polygon, then bicycle_no
        reason = self.apply_pipeline_to_mock(metadata={"nodes": [1,2,1], "tags": {"bicycle": "no"}}, keep_polygons=False)
        # Based on order: polygon filter comes first.
        self.assertEqual(reason, FilterReason.POLYGON)

    def test_pipeline_bicycle_no_after_polygon_pass(self):
        reason = self.apply_pipeline_to_mock(metadata={"nodes": [1,2,3], "tags": {"bicycle": "no"}}, keep_polygons=False)
        self.assertEqual(reason, FilterReason.BICYCLE_NO)


    def test_pipeline_waterway_filtered(self):
        reason = self.apply_pipeline_to_mock(metadata={"tags": {"waterway": "river"}})
        self.assertEqual(reason, FilterReason.WATERWAY)

    def test_pipeline_railway_filtered(self):
        reason = self.apply_pipeline_to_mock(metadata={"tags": {"railway": "main"}})
        self.assertEqual(reason, FilterReason.RAILWAY)

    def test_pipeline_bicycle_yes_overrides_waterway(self):
        reason = self.apply_pipeline_to_mock(metadata={"tags": {"waterway": "canal", "bicycle": "yes"}})
        self.assertEqual(reason, FilterReason.NONE)

    def test_pipeline_cycleway_overrides_railway(self):
        reason = self.apply_pipeline_to_mock(metadata={"tags": {"railway": "track", "highway": "cycleway"}})
        self.assertEqual(reason, FilterReason.NONE)

    def test_pipeline_all_clear(self):
        reason = self.apply_pipeline_to_mock(metadata={"tags": {"highway": "residential"}})
        self.assertEqual(reason, FilterReason.NONE)

    def test_pipeline_bicycle_no_and_waterway(self):
        # bicycle=no should take precedence over waterway if both apply
        # Order: bicycle_no is before waterway_filter in pipeline
        reason = self.apply_pipeline_to_mock(metadata={"tags": {"bicycle": "no", "waterway": "river"}})
        self.assertEqual(reason, FilterReason.BICYCLE_NO)

if __name__ == '__main__':
    unittest.main()
