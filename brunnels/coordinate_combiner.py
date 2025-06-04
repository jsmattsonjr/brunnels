#!/usr/bin/env python3
"""
Directional coordinate combining for OSM ways.

Handles the complex logic of combining coordinates from adjacent OpenStreetMap ways
in the correct directional order, accounting for how the ways actually connect
via shared nodes.
"""

from typing import List, Optional, Set, TYPE_CHECKING
from dataclasses import dataclass
import logging

if TYPE_CHECKING:
    from .brunnel_way import BrunnelWay
    from .geometry import Position

logger = logging.getLogger(__name__)


@dataclass
class NodeConnection:
    """Represents how two components connect via shared nodes."""

    component1_idx: int
    component2_idx: int
    shared_nodes: Set[int]  # OSM node IDs that are shared
    component1_end: str  # 'first' or 'last'
    component2_end: str  # 'first' or 'last'


class DirectionalCoordinateCombiner:
    """
    Handles proper directional combining of adjacent OSM way coordinates.

    This class solves the problem that OSM ways can be oriented in any direction,
    so when combining adjacent ways into a single polyline, we need to determine
    the correct direction for each way to maintain spatial continuity.
    """

    def __init__(self, components: List["BrunnelWay"]):
        """
        Initialize combiner with list of adjacent components.

        Args:
            components: List of BrunnelWay objects in route order

        Raises:
            ValueError: If components don't satisfy adjacency assumptions
        """
        self.components = components
        self.connections: List[NodeConnection] = []
        self._validate_and_analyze_connections()

    def _validate_and_analyze_connections(self) -> None:
        """
        Validate assumptions and analyze how components connect.

        Assumptions validated:
        1. Adjacent ways share exactly one node
        2. Internal ways share one endpoint with each neighbor
        """
        if len(self.components) < 2:
            return

        # Build connection graph
        for i in range(len(self.components) - 1):
            connection = self._find_connection(i, i + 1)
            if connection is None:
                raise ValueError(
                    f"Components {i} and {i+1} don't share exactly one node"
                )
            self.connections.append(connection)

        # Validate assumptions
        self._validate_assumptions()

    def _find_connection(self, idx1: int, idx2: int) -> Optional[NodeConnection]:
        """
        Analyze how two adjacent components connect via shared nodes.

        Args:
            idx1: Index of first component
            idx2: Index of second component

        Returns:
            NodeConnection object describing the connection, or None if invalid
        """
        comp1 = self.components[idx1]
        comp2 = self.components[idx2]

        nodes1 = comp1.metadata.get("nodes", [])
        nodes2 = comp2.metadata.get("nodes", [])

        if not nodes1 or not nodes2:
            return None

        shared_nodes = set(nodes1) & set(nodes2)

        # Must share exactly one node
        if len(shared_nodes) != 1:
            return None

        shared_node = list(shared_nodes)[0]

        # Determine which end of each component the shared node is at
        comp1_end = None
        comp2_end = None

        if nodes1[0] == shared_node:
            comp1_end = "first"
        elif nodes1[-1] == shared_node:
            comp1_end = "last"
        else:
            return None  # Shared node is internal, not an endpoint

        if nodes2[0] == shared_node:
            comp2_end = "first"
        elif nodes2[-1] == shared_node:
            comp2_end = "last"
        else:
            return None  # Shared node is internal, not an endpoint

        return NodeConnection(idx1, idx2, shared_nodes, comp1_end, comp2_end)

    def _validate_assumptions(self) -> None:
        """
        Validate the stated assumptions about adjacent ways.

        Raises:
            ValueError: If assumptions are violated
        """

        # Assumption 1: Abutting ways share one and only one node
        for conn in self.connections:
            if len(conn.shared_nodes) != 1:
                raise ValueError(
                    f"Components {conn.component1_idx} and {conn.component2_idx} "
                    f"share {len(conn.shared_nodes)} nodes, expected exactly 1"
                )

        # Assumption 2: Internal ways share one endpoint with each neighbor
        for i in range(1, len(self.components) - 1):  # Internal components
            prev_conn = self.connections[i - 1]  # Connection to previous
            next_conn = self.connections[i]  # Connection to next

            # This component should appear as component2 in prev_conn and component1 in next_conn
            if prev_conn.component2_idx != i or next_conn.component1_idx != i:
                raise ValueError(
                    f"Connection indexing error for internal component {i}"
                )

            # The ends used in connections should be different (one endpoint each)
            prev_end = (
                prev_conn.component2_end
            )  # How this component connects to previous
            next_end = next_conn.component1_end  # How this component connects to next

            if prev_end == next_end:
                raise ValueError(
                    f"Internal component {i} uses same endpoint ('{prev_end}') "
                    f"for both neighbors - violates assumption 2"
                )

    def combine_coordinates(self) -> List["Position"]:
        """
        Combine coordinates in the correct directional order.

        Returns:
            List of Position objects representing the properly connected polyline
        """
        if not self.components:
            return []

        if len(self.components) == 1:
            return self.components[0].coords[:]

        # Determine direction for each component
        component_directions = self._determine_directions()

        # Combine coordinates
        result = []
        for i, component in enumerate(self.components):
            coords = component.coords

            # Apply direction
            if component_directions[i] == "reverse":
                coords = coords[::-1]

            if i == 0:
                # First component - add all coordinates
                result.extend(coords)
            else:
                # Subsequent components - skip the shared coordinate
                result.extend(coords[1:])

        return result

    def _determine_directions(self) -> List[str]:
        """
        Determine which direction each component should go to maintain continuity.

        Returns:
            List of direction strings ('forward' or 'reverse') for each component
        """
        if not self.components:
            return []
        if len(self.components) == 1:
            # Single component is always considered "forward" in its own context
            return ["forward"]

        directions = []
        first_connection = self.connections[0]

        # Determine initial direction for the first component based on its connection to the second.
        # If the first component connects via its 'first' node, it implies it might be "backward"
        # relative to the start of the sequence.
        if first_connection.component1_end == "first":
            directions.append("reverse")
        else: # component1_end == "last"
            directions.append("forward")

        for i, conn in enumerate(self.connections):
            # Determine direction of next component (self.components[i+1])
            # based on the already determined direction of the current component (self.components[i])
            prev_direction = directions[i]
            prev_end = conn.component1_end # How self.components[i] connects
            next_end = conn.component2_end # How self.components[i+1] connects

            # If previous component's actual direction is reverse, its connection end is flipped
            if prev_direction == "reverse":
                prev_end = "last" if prev_end == "first" else "first"

            # Determine next component's direction
            if prev_end == "last" and next_end == "first":
                # e.g. CompA (ends) -> CompB (starts) : CompB is forward
                next_direction = "forward"
            elif prev_end == "last" and next_end == "last":
                # e.g. CompA (ends) -> CompB (ends) : CompB is reverse
                next_direction = "reverse"
            elif prev_end == "first" and next_end == "first":
                # e.g. CompA (starts) -> CompB (starts) : CompB is reverse
                next_direction = "reverse"
            elif prev_end == "first" and next_end == "last":
                # e.g. CompA (starts) -> CompB (ends) : CompB is forward
                next_direction = "forward"
            else:
                # This case should ideally not be reached if component1_end and component2_end are always 'first' or 'last'
                raise ValueError(
                    f"Unexpected connection pattern: {prev_end}->{next_end} for components {conn.component1_idx} and {conn.component2_idx}"
                )

            # This direction is for self.components[i+1]
            # If 'directions' list has N elements, they are for components 0 to N-1.
            # We are calculating direction for component i+1.
            if len(directions) == i + 1: # If we are about to add direction for component i+1
                 directions.append(next_direction)
            else:
                # This case should not happen if logic is correct, implies mismatch in loop / list population
                raise RuntimeError(f"Directions list length {len(directions)} out of sync with component index {i+1}")

        return directions


def combine_osm_way_coordinates(components: List["BrunnelWay"]) -> List["Position"]:
    """
    Convenience function to combine OSM way coordinates in correct directional order.

    Args:
        components: List of adjacent BrunnelWay objects

    Returns:
        List of Position objects representing the properly connected polyline

    Raises:
        ValueError: If components don't satisfy adjacency requirements
    """
    combiner = DirectionalCoordinateCombiner(components)
    return combiner.combine_coordinates()
