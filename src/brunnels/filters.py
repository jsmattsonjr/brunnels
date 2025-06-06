# src/brunnels/filters.py
import typing
from .brunnel import FilterReason
from functools import partial

# Import for type hints only, will be string literals in function signatures
if typing.TYPE_CHECKING:
    from .brunnel_way import BrunnelWay
    from .filter_pipeline import FilterPipeline


def check_polygon_filter(brunnel: 'BrunnelWay', keep_polygons: bool) -> FilterReason:
    if not keep_polygons:
        nodes = brunnel.metadata.get("nodes", [])
        if len(nodes) >= 2 and nodes[0] == nodes[-1]:
            return FilterReason.POLYGON
    return FilterReason.NONE

def check_bicycle_no_filter(brunnel: 'BrunnelWay') -> FilterReason:
    if brunnel.metadata.get("tags", {}).get("bicycle") == "no":
        return FilterReason.BICYCLE_NO
    return FilterReason.NONE

def check_waterway_filter(brunnel: 'BrunnelWay') -> FilterReason:
    tags = brunnel.metadata.get("tags", {})
    if "waterway" in tags:
        if "bicycle" in tags and tags["bicycle"] != "no":
            return FilterReason.NONE
        if tags.get("highway") == "cycleway":
            return FilterReason.NONE
        return FilterReason.WATERWAY
    return FilterReason.NONE

def check_railway_filter(brunnel: 'BrunnelWay') -> FilterReason:
    tags = brunnel.metadata.get("tags", {})
    if "railway" in tags and tags["railway"] != "abandoned":
        if "bicycle" in tags and tags["bicycle"] != "no":
            return FilterReason.NONE
        if tags.get("highway") == "cycleway":
            return FilterReason.NONE
        return FilterReason.RAILWAY
    return FilterReason.NONE

def create_standard_brunnel_filter_pipeline(keep_polygons: bool = False, enable_tag_filtering: bool = True) -> 'FilterPipeline':
    # Moved import here to break circular dependency
    from .filter_pipeline import FilterPipeline

    pipeline = FilterPipeline()
    if enable_tag_filtering:
        pipeline.add_filter(partial(check_polygon_filter, keep_polygons=keep_polygons))
        pipeline.add_filter(check_bicycle_no_filter)
        pipeline.add_filter(check_waterway_filter)
        pipeline.add_filter(check_railway_filter)
    return pipeline
