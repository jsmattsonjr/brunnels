#!/usr/bin/env python3
"""
Compound BrunnelWay implementation for handling adjacent brunnel segments.
"""

from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field
import logging

from .geometry import Position
from .brunnel import Brunnel, BrunnelType, FilterReason, RouteSpan
from .coordinate_combiner import combine_osm_way_coordinates
from .brunnel_way import BrunnelWay

logger = logging.getLogger(__name__)


@dataclass
class CompoundBrunnelWay(Brunnel):
    """
    A compound brunnel way consisting of multiple adjacent BrunnelWay segments.

    The segments are ordered according to route progression, with coordinates
    and node ordering normalized to maintain consistency.
    """

    components: List[BrunnelWay]

    # Memoized properties
    _coordinates: Optional[List[Position]] = field(default=None, init=False, repr=False)
    _combined_metadata: Optional[Dict[str, Any]] = field(
        default=None, init=False, repr=False
    )

    def __init__(
        self,
        components: List[BrunnelWay],
        brunnel_type: BrunnelType,
        contained_in_route: bool = False,
        filter_reason: FilterReason = FilterReason.NONE,
        route_span: Optional[RouteSpan] = None,
    ):
        super().__init__(brunnel_type, contained_in_route, filter_reason, route_span)
        self.components = components
        self._coordinates = None
        self._combined_metadata = None
        self._validate_components()

    def _validate_components(self):
        """Validate and normalize the compound brunnel way."""
        if not self.components:
            raise ValueError("CompoundBrunnelWay must have at least one component")

        # Verify all components are the same type
        first_type = self.components[0].brunnel_type
        if not all(comp.brunnel_type == first_type for comp in self.components):
            raise ValueError("All components must be the same brunnel type")

        # Verify all components have FilterReason.NONE (they're being combined)
        if not all(comp.filter_reason == FilterReason.NONE for comp in self.components):
            raise ValueError(
                "All components must have FilterReason.NONE to be combined"
            )

        # Ensure brunnel_type matches components
        if self.brunnel_type != first_type:
            self.brunnel_type = first_type

    @property
    def coordinate_list(self) -> List[Position]:
        """Return the combined coordinate list for this compound geometry."""
        if self._coordinates is None:
            self._coordinates = self._compute_combined_coordinates()
        return self._coordinates

    def get_id(self) -> str:
        """Get a string identifier for this compound brunnel."""
        return self.get_combined_metadata()["id"]

    def _compute_combined_coordinates(self) -> List[Position]:
        """
        Compute the combined coordinates from all components in correct directional order.

        Returns:
            List of Position objects representing the full compound brunnel
        """
        if not self.components:
            return []

        try:
            # Use sophisticated directional combining
            return combine_osm_way_coordinates(self.components)
        except Exception as e:
            logger.error(f"Failed to combine coordinates directionally: {e}")
            logger.warning("Falling back to naive concatenation")
            # Fallback to naive approach for robustness
            return self._naive_combine_coordinates()

    def _naive_combine_coordinates(self) -> List[Position]:
        """
        Fallback naive coordinate combination (current approach).

        Returns:
            List of Position objects using simple concatenation
        """
        combined_coords = []
        for i, component in enumerate(self.components):
            if i == 0:
                combined_coords.extend(component.coords)
            else:
                if component.coords:
                    combined_coords.extend(component.coords[1:])
        return combined_coords

    def get_combined_metadata(self) -> Dict[str, Any]:
        """
        Get combined metadata for popup display.

        Returns:
            Dictionary containing information about all components
        """
        if self._combined_metadata is None:
            self._combined_metadata = self._compute_combined_metadata()
        return self._combined_metadata

    def _compute_combined_metadata(self) -> Dict[str, Any]:
        """
        Compute combined metadata from all components.

        Returns:
            Dictionary with combined information
        """
        combined = {
            "type": "compound",
            "brunnel_type": self.brunnel_type.value,
            "component_count": len(self.components),
            "components": [],
        }

        # Collect OSM IDs
        osm_ids = []
        total_length = 0.0

        for i, component in enumerate(self.components):
            comp_info = {
                "index": i,
                "id": component.get_id(),
                "tags": component.metadata.get("tags", {}),
                "metadata": component.metadata,
            }

            # Add route span info if available
            if component.route_span:
                comp_info["route_span"] = {
                    "start_km": component.route_span.start_distance_km,
                    "end_km": component.route_span.end_distance_km,
                    "length_km": component.route_span.length_km,
                }
                total_length += component.route_span.length_km

            combined["components"].append(comp_info)
            osm_ids.append(component.get_id())

        # Add summary information
        combined["id"] = ";".join(osm_ids)
        combined["total_length_km"] = total_length

        combined["tags"] = {}

        return combined

    def get_primary_name(self) -> str:
        """
        Get the primary name for this compound brunnel.

        Returns:
            The name from the first component that has one, or "unnamed"
        """
        for component in self.components:
            name = component.metadata.get("tags", {}).get("name")
            if name:
                return name
        return "unnamed"

    def get_display_name(self) -> str:
        """Get the display name for this compound brunnel."""
        return self.get_primary_name()

    def get_short_description(self) -> str:
        """Get a short description for logging."""
        brunnel_type = self.brunnel_type.value.capitalize()
        name = self.get_display_name()
        component_count = len(self.components)
        return f"Compound {brunnel_type}: {name} ({self.get_id()}) [{component_count} segments]"

    def is_aligned_with_route(self, route, tolerance_degrees: float) -> bool:
        """
        Check if this compound brunnel's bearing is aligned with the route at their closest point.
        Uses the first component's alignment as representative of the entire compound brunnel.

        Args:
            route: Route object representing the route
            tolerance_degrees: Allowed bearing deviation in degrees

        Returns:
            True if compound brunnel is aligned with route within tolerance, False otherwise
        """
        if not self.components:
            return False

        # Use the first component as representative for alignment checking
        return self.components[0].is_aligned_with_route(route, tolerance_degrees)

    def to_html(self) -> str:
        """
        Format this compound brunnel's metadata into HTML for popup display.

        Returns:
            HTML-formatted string with compound brunnel information
        """
        html_parts = []

        # Header with compound information
        brunnel_type = self.brunnel_type.value.capitalize()
        component_count = len(self.components)
        primary_name = self.get_primary_name()

        html_parts.append(
            f"<b>Compound {brunnel_type}</b> ({component_count} segments)"
        )

        if primary_name != "unnamed":
            html_parts.append(f"<br><b>Name:</b> {primary_name}")

        # Route span information
        if self.route_span:
            span = self.route_span
            html_parts.append(
                f"<br><b>Route Span:</b> {span.start_distance_km:.2f} - {span.end_distance_km:.2f} km "
                f"(length: {span.length_km:.2f} km)"
            )

        # Combined OSM ID
        combined_metadata = self.get_combined_metadata()
        html_parts.append(f"<br><b>Combined OSM ID:</b> {combined_metadata['id']}")

        # Component details
        html_parts.append("<br><br><b>Component Segments:</b>")

        for i, component in enumerate(self.components):
            html_parts.append(f"<br><br><b>Segment {i+1}:</b>")

            # Component name
            comp_tags = component.metadata.get("tags", {})
            if "name" in comp_tags:
                html_parts.append(f"<br>&nbsp;&nbsp;<b>Name:</b> {comp_tags['name']}")

            # Component OSM ID
            html_parts.append(f"<br>&nbsp;&nbsp;<b>OSM ID:</b> {component.get_id()}")

            # Component route span
            if component.route_span:
                span = component.route_span
                html_parts.append(
                    f"<br>&nbsp;&nbsp;<b>Span:</b> {span.start_distance_km:.2f} - {span.end_distance_km:.2f} km "
                    f"({span.length_km:.2f} km)"
                )

            # Component tags (excluding name which we already showed)
            remaining_tags = {k: v for k, v in comp_tags.items() if k != "name"}
            if remaining_tags:
                html_parts.append("<br>&nbsp;&nbsp;<b>Tags:</b>")
                for key, value in sorted(remaining_tags.items()):
                    html_parts.append(
                        f"<br>&nbsp;&nbsp;&nbsp;&nbsp;<i>{key}:</i> {value}"
                    )

        return "".join(html_parts)

    @classmethod
    def detect_adjacent_groups(cls, brunnels: List[BrunnelWay]) -> List[List[int]]:
        """
        Detect groups of adjacent brunnels that can be combined into compound brunnels.

        Args:
            brunnels: List of all brunnels to analyze

        Returns:
            List of lists, where each inner list contains indices of adjacent brunnels
            that should be combined (only groups with 2+ members are returned)
        """
        # Only consider contained brunnels with route spans
        contained_indices = [
            i
            for i, b in enumerate(brunnels)
            if b.contained_in_route
            and b.route_span is not None
            and b.filter_reason == FilterReason.NONE
        ]

        if len(contained_indices) < 2:
            return []

        # Sort by start distance along route
        contained_indices.sort(key=lambda i: brunnels[i].route_span.start_distance_km)  # type: ignore

        # Group by brunnel type first
        type_groups = {}
        for idx in contained_indices:
            brunnel_type = brunnels[idx].brunnel_type
            if brunnel_type not in type_groups:
                type_groups[brunnel_type] = []
            type_groups[brunnel_type].append(idx)

        adjacent_groups = []

        # Check each type group for adjacent segments
        for brunnel_type, indices in type_groups.items():
            if len(indices) < 2:
                continue

            current_group = [indices[0]]

            for i in range(1, len(indices)):
                curr_idx = indices[i]
                prev_idx = indices[i - 1]

                curr_brunnel = brunnels[curr_idx]
                prev_brunnel = brunnels[prev_idx]

                # Check if they share a node using the new method
                if prev_brunnel.shares_node_with(curr_brunnel):
                    # Add to current group
                    current_group.append(curr_idx)
                else:
                    # End current group and start new one
                    if len(current_group) > 1:
                        adjacent_groups.append(current_group)
                    current_group = [curr_idx]

            # Don't forget the last group
            if len(current_group) > 1:
                adjacent_groups.append(current_group)

        return adjacent_groups

    @classmethod
    def create_from_brunnels(cls, brunnels: List[BrunnelWay]) -> List[Brunnel]:
        """
        Create compound brunnels from adjacent segments and return the modified list.

        Args:
            brunnels: List of all brunnels (original list is not modified)

        Returns:
            New list with compound brunnels replacing adjacent groups
        """
        # Find adjacent groups
        adjacent_groups = cls.detect_adjacent_groups(brunnels)

        if not adjacent_groups:
            logger.debug("No adjacent brunnels found for compounding")
            return list(brunnels)  # Return new list typed as List[Brunnel]

        logger.debug(
            f"Found {len(adjacent_groups)} groups of adjacent brunnels to compound"
        )

        # Create new list with compound brunnels
        result = []
        processed_indices = set()

        # Add compound brunnels
        compound_count = 0
        for group_indices in adjacent_groups:
            if len(group_indices) < 2:
                continue

            components = [brunnels[i] for i in group_indices]

            # Create compound brunnel
            try:
                compound = cls(
                    components=components,
                    brunnel_type=components[0].brunnel_type,
                    contained_in_route=True,  # All components are contained
                    filter_reason=FilterReason.NONE,
                )

                # Calculate combined route span
                start_km = min(
                    comp.route_span.start_distance_km
                    for comp in components
                    if comp.route_span
                )
                end_km = max(
                    comp.route_span.end_distance_km
                    for comp in components
                    if comp.route_span
                )
                compound.route_span = RouteSpan(start_km, end_km, end_km - start_km)

                result.append(compound)
                processed_indices.update(group_indices)
                compound_count += 1

                # Log the compound creation
                component_ids = [comp.get_id() for comp in components]
                logger.debug(
                    f"Created compound {components[0].brunnel_type.value}: {';'.join(component_ids)}"
                )

            except Exception as e:
                logger.warning(
                    f"Failed to create compound brunnel from group {group_indices}: {e}"
                )
                # Fall back to individual brunnels
                for idx in group_indices:
                    if idx not in processed_indices:
                        result.append(brunnels[idx])
                        processed_indices.add(idx)

        # Add remaining individual brunnels
        for i, brunnel in enumerate(brunnels):
            if i not in processed_indices:
                result.append(brunnel)

        if compound_count > 0:
            logger.debug(
                f"Created {compound_count} compound brunnels from {len(adjacent_groups)} groups"
            )

        return result

    def __len__(self) -> int:
        """Return the number of components in this compound brunnel."""
        return len(self.components)

    def __getitem__(self, index: int) -> BrunnelWay:
        """Allow indexing into components."""
        return self.components[index]

    def __iter__(self):
        """Allow iteration over components."""
        return iter(self.components)
