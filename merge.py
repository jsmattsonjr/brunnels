#!/usr/bin/env python3
"""
Brunnel merging operations for combining adjacent segments.
"""

from typing import Optional, Tuple, List, Dict, Any
import logging
from brunnel_way import BrunnelWay, Direction, FilterReason, RouteSpan

logger = logging.getLogger(__name__)


def detect_shared_node(
    brunnel1: BrunnelWay, brunnel2: BrunnelWay
) -> Optional[Tuple[Direction, Direction]]:
    """
    Detect if two brunnels share a node and return their relative directions.

    Args:
        brunnel1: First brunnel
        brunnel2: Second brunnel (should be adjacent to first in route order)

    Returns:
        Tuple of (brunnel1_direction, brunnel2_direction) if they share a node,
        None if they don't share a node or don't have node data
    """
    # Check if both brunnels have node data
    nodes1 = brunnel1.metadata.get("nodes")
    nodes2 = brunnel2.metadata.get("nodes")

    if not nodes1 or not nodes2 or len(nodes1) < 2 or len(nodes2) < 2:
        return None

    first_node1 = nodes1[0]
    last_node1 = nodes1[-1]
    first_node2 = nodes2[0]
    last_node2 = nodes2[-1]

    # Check all four possible connection patterns
    if last_node1 == first_node2:
        # brunnel1 (forward) connects to brunnel2 (forward)
        return (Direction.FORWARD, Direction.FORWARD)
    elif last_node1 == last_node2:
        # brunnel1 (forward) connects to brunnel2 (reverse)
        return (Direction.FORWARD, Direction.REVERSE)
    elif first_node1 == first_node2:
        # brunnel1 (reverse) connects to brunnel2 (forward)
        return (Direction.REVERSE, Direction.FORWARD)
    elif first_node1 == last_node2:
        # brunnel1 (reverse) connects to brunnel2 (reverse)
        return (Direction.REVERSE, Direction.REVERSE)

    # No shared nodes found
    return None


def merge_brunnels(
    brunnel1: BrunnelWay, brunnel2: BrunnelWay, directions: Tuple[Direction, Direction]
) -> None:
    """
    Merge brunnel2 into brunnel1, modifying brunnel1 in-place.

    Args:
        brunnel1: Target brunnel to merge into (modified in-place)
        brunnel2: Source brunnel to merge from
        directions: Tuple of (brunnel1_direction, brunnel2_direction) from detect_shared_node
    """
    dir1, dir2 = directions

    # Merge tags
    tags1 = brunnel1.metadata.get("tags", {})
    tags2 = brunnel2.metadata.get("tags", {})

    merged_tags = tags1.copy()
    for key, value2 in tags2.items():
        if key not in merged_tags:
            # Tag only exists in brunnel2, add it
            merged_tags[key] = value2
        elif merged_tags[key] != value2:
            # Tag exists in both but with different values, warn and keep brunnel1's value
            logger.warning(
                f"Tag conflict during merge: {key}='{merged_tags[key]}' vs '{value2}'; keeping first value"
            )

    # Merge nodes with correct ordering (not as sets)
    nodes1 = brunnel1.metadata.get("nodes", [])[:]
    nodes2 = brunnel2.metadata.get("nodes", [])[:]

    # Apply direction-based concatenation for nodes too
    if dir1 == Direction.REVERSE:
        nodes1 = list(reversed(nodes1))
    if dir2 == Direction.REVERSE:
        nodes2 = list(reversed(nodes2))

    # Concatenate nodes, removing the duplicate shared node
    if nodes2:
        merged_nodes = nodes1 + nodes2[1:]
    else:
        merged_nodes = nodes1

    # Merge coords with correct ordering
    coords1 = brunnel1.coords[:]
    coords2 = brunnel2.coords[:]

    # Apply direction-based concatenation
    if dir1 == Direction.REVERSE:
        coords1 = list(reversed(coords1))
    if dir2 == Direction.REVERSE:
        coords2 = list(reversed(coords2))

    # Concatenate, removing the duplicate shared coordinate
    if coords2:
        merged_coords = coords1 + coords2[1:]
    else:
        merged_coords = coords1

    # Merge geometry metadata similarly
    geometry1 = brunnel1.metadata.get("geometry", [])
    geometry2 = brunnel2.metadata.get("geometry", [])

    if dir1 == Direction.REVERSE:
        geometry1 = list(reversed(geometry1))
    if dir2 == Direction.REVERSE:
        geometry2 = list(reversed(geometry2))

    # Concatenate geometry, removing duplicate
    if geometry2:
        merged_geometry = geometry1 + geometry2[1:]
    else:
        merged_geometry = geometry1

    # Merge bounds (union of bounding boxes)
    bounds1 = brunnel1.metadata.get("bounds", {})
    bounds2 = brunnel2.metadata.get("bounds", {})

    merged_bounds = bounds1.copy()
    if bounds1 and bounds2:
        merged_bounds = {
            "minlat": min(
                bounds1.get("minlat", float("inf")), bounds2.get("minlat", float("inf"))
            ),
            "minlon": min(
                bounds1.get("minlon", float("inf")), bounds2.get("minlon", float("inf"))
            ),
            "maxlat": max(
                bounds1.get("maxlat", float("-inf")),
                bounds2.get("maxlat", float("-inf")),
            ),
            "maxlon": max(
                bounds1.get("maxlon", float("-inf")),
                bounds2.get("maxlon", float("-inf")),
            ),
        }
    elif bounds2:
        merged_bounds = bounds2.copy()

    # Concatenate OSM IDs
    id1 = str(brunnel1.metadata.get("id", "unknown"))
    id2 = str(brunnel2.metadata.get("id", "unknown"))
    merged_id = f"{id1};{id2}"

    # Merge route spans (start of brunnel1, end of brunnel2)
    merged_route_span = None
    if brunnel1.route_span and brunnel2.route_span:
        merged_route_span = RouteSpan(
            start_distance_km=brunnel1.route_span.start_distance_km,
            end_distance_km=brunnel2.route_span.end_distance_km,
            length_km=brunnel2.route_span.end_distance_km
            - brunnel1.route_span.start_distance_km,
        )
    elif brunnel1.route_span:
        merged_route_span = brunnel1.route_span
    elif brunnel2.route_span:
        merged_route_span = brunnel2.route_span

    # Update brunnel1 with merged data
    brunnel1.coords = merged_coords
    brunnel1.route_span = merged_route_span

    # Clear memoized LineString since coords changed
    brunnel1._linestring = None

    # Update metadata
    merged_metadata = brunnel1.metadata.copy()
    merged_metadata["tags"] = merged_tags
    merged_metadata["nodes"] = merged_nodes
    merged_metadata["geometry"] = merged_geometry
    merged_metadata["bounds"] = merged_bounds
    merged_metadata["id"] = merged_id

    # Copy other metadata from brunnel2 that's not already handled
    for key, value in brunnel2.metadata.items():
        if key not in ["tags", "nodes", "geometry", "bounds", "id"]:
            if key not in merged_metadata:
                merged_metadata[key] = value

    brunnel1.metadata = merged_metadata

    # Mark brunnel2 as merged
    brunnel2.filter_reason = FilterReason.MERGED


def merge_adjacent_brunnels(brunnels: List[BrunnelWay]) -> int:
    """
    Merge adjacent brunnels that share nodes and are of the same type.
    Also handles removal of merged brunnels from the list.

    Args:
        brunnels: List of all brunnels (modified in-place)

    Returns:
        Number of merges performed
    """
    # Find included brunnel indices
    included_brunnel_indices = [
        i for i, b in enumerate(brunnels) if b.contained_in_route
    ]

    if not included_brunnel_indices:
        return 0

    # Sort by start km
    included_brunnel_indices.sort(
        key=lambda i: (
            brunnels[i].route_span.start_distance_km  # type: ignore[union-attr]
        )
    )

    # Perform merging
    merge_count = 0
    updated_indices = included_brunnel_indices[:]

    i = 0
    while i < len(updated_indices) - 1:
        idx1 = updated_indices[i]
        idx2 = updated_indices[i + 1]
        brunnel1 = brunnels[idx1]
        brunnel2 = brunnels[idx2]

        # Only check same-type brunnels
        if brunnel1.brunnel_type == brunnel2.brunnel_type:
            shared_result = detect_shared_node(brunnel1, brunnel2)
            if shared_result:
                logger.debug(
                    f"Merging {brunnel1.brunnel_type.value} {brunnel2.metadata.get('id', 'unknown')} "
                    f"into {brunnel1.metadata.get('id', 'unknown')}"
                )

                # Perform the merge
                merge_brunnels(brunnel1, brunnel2, shared_result)
                merge_count += 1

                # Remove the merged brunnel from updated_indices
                updated_indices.pop(i + 1)

                # Don't increment i, check if the next brunnel can also be merged
                continue

        # Move to next brunnel
        i += 1

    if merge_count > 0:
        logger.debug(f"Merged {merge_count} adjacent brunnels")

    # Remove merged brunnels from the full list
    original_count = len(brunnels)
    brunnels[:] = [b for b in brunnels if b.filter_reason != FilterReason.MERGED]
    removed_count = original_count - len(brunnels)
    if removed_count > 0:
        logger.debug(f"Removed {removed_count} merged brunnels from full list")

    return merge_count


def log_final_included_brunnels(brunnels: List[BrunnelWay]) -> None:
    """
    Log the final list of brunnels that are included in the route (after all filtering).
    This shows the actual brunnels that will appear on the map.

    Args:
        brunnels: List of all brunnels to check
    """
    # Find final included brunnels (those that are contained and not filtered)
    included_brunnels = [b for b in brunnels if b.contained_in_route]

    if not included_brunnels:
        logger.info("No brunnels included in final map")
        return

    # Sort by start distance along route
    included_brunnels.sort(
        key=lambda b: (b.route_span.start_distance_km if b.route_span else 0.0)
    )

    logger.info(f"Included brunnels (final):")
    for brunnel in included_brunnels:
        brunnel_type = brunnel.brunnel_type.value.capitalize()
        name = brunnel.metadata.get("tags", {}).get("name", "unnamed")
        osm_id = brunnel.metadata.get("id", "unknown")

        if brunnel.route_span:
            span_data = f"{brunnel.route_span.start_distance_km:.2f}-{brunnel.route_span.end_distance_km:.2f} km (length: {brunnel.route_span.length_km:.2f} km)"
        else:
            span_data = "no span data"

        logger.info(f"  {brunnel_type}: {name} ({osm_id}) {span_data}")
