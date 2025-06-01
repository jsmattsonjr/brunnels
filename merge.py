#!/usr/bin/env python3
"""
Brunnel merging operations for combining adjacent segments.
"""

from typing import Optional, Tuple
import logging
from models import BrunnelWay, Direction

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
