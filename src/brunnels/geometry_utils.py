#!/usr/bin/env python3
"""
Geometry and distance calculation utilities for route analysis.
"""

from typing import List, Tuple, Optional
import logging

from .geometry import Position


logger = logging.getLogger(__name__)


def find_closest_segments(
    polyline1: List[Position], polyline2: List[Position]
) -> Tuple[
    Optional[Tuple[int, Position, Position]], Optional[Tuple[int, Position, Position]]
]:
    """
    Find the closest segments between two polylines.

    Args:
        polyline1: First polyline as list of positions
        polyline2: Second polyline as list of positions

    Returns:
        Tuple of (closest_segment1, closest_segment2) where each is:
        (segment_index, segment_start, segment_end) or None if no valid segments found
    """
    if len(polyline1) < 2 or len(polyline2) < 2:
        return None, None

    min_distance = float("inf")
    best_seg1 = None
    best_seg2 = None

    # Check each segment of polyline1 against each segment of polyline2
    for i in range(len(polyline1) - 1):
        seg1_start = polyline1[i]
        seg1_end = polyline1[i + 1]

        for j in range(len(polyline2) - 1):
            seg2_start = polyline2[j]
            seg2_end = polyline2[j + 1]

            # Find closest points between segments
            # Check distance from seg1_start to seg2
            dist1, _, _ = seg1_start.to_line_segment_distance_and_projection(
                seg2_start, seg2_end
            )
            # Check distance from seg1_end to seg2
            dist2, _, _ = seg1_end.to_line_segment_distance_and_projection(
                seg2_start, seg2_end
            )
            # Check distance from seg2_start to seg1
            dist3, _, _ = seg2_start.to_line_segment_distance_and_projection(
                seg1_start, seg1_end
            )
            # Check distance from seg2_end to seg1
            dist4, _, _ = seg2_end.to_line_segment_distance_and_projection(
                seg1_start, seg1_end
            )

            # Use minimum distance between all combinations
            segment_distance = min(dist1, dist2, dist3, dist4)

            if segment_distance < min_distance:
                min_distance = segment_distance
                best_seg1 = (i, seg1_start, seg1_end)
                best_seg2 = (j, seg2_start, seg2_end)

    return best_seg1, best_seg2


def bearings_aligned(
    bearing1: float, bearing2: float, tolerance_degrees: float
) -> bool:
    """
    Check if two bearings are aligned within tolerance (same direction or opposite direction).

    Args:
        bearing1: First bearing in degrees (0-360)
        bearing2: Second bearing in degrees (0-360)
        tolerance_degrees: Allowed deviation in degrees

    Returns:
        True if bearings are aligned within tolerance, False otherwise
    """
    # Calculate difference and normalize to 0-180 range
    diff = abs(bearing1 - bearing2)
    diff = min(diff, 360 - diff)  # Handle wraparound (e.g., 10° and 350°)

    # Check if aligned in same direction or opposite direction
    same_direction = diff <= tolerance_degrees
    opposite_direction = abs(diff - 180) <= tolerance_degrees

    return same_direction or opposite_direction
