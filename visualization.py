#!/usr/bin/env python3
"""
Route visualization using folium maps with support for compound brunnels.
"""

from typing import List, Dict, Any, Union
import logging
import folium
from brunnel_way import BrunnelWay, BrunnelType, FilterReason
from compound_brunnel_way import CompoundBrunnelWay
from route import Route

logger = logging.getLogger(__name__)

# Type alias for brunnel objects
BrunnelLike = Union[BrunnelWay, CompoundBrunnelWay]


def _format_complex_value(key: str, value: Any, indent_level: int = 0) -> str:
    """
    Format complex values (dicts, lists) into readable HTML with proper indentation.

    Args:
        key: The key name
        value: The value to format
        indent_level: Current indentation level

    Returns:
        Formatted HTML string
    """
    indent = "&nbsp;" * (indent_level * 4)

    if isinstance(value, dict):
        if not value:
            return f"{indent}<i>{key}:</i> {{}}"

        parts = [f"{indent}<i>{key}:</i>"]
        for k, v in value.items():
            if isinstance(v, (dict, list)):
                parts.append(_format_complex_value(k, v, indent_level + 1))
            else:
                nested_indent = "&nbsp;" * ((indent_level + 1) * 4)
                parts.append(f"{nested_indent}<i>{k}:</i> {v}")
        return "<br>".join(parts)

    elif isinstance(value, list):
        if not value:
            return f"{indent}<i>{key}:</i> []"

        parts = [f"{indent}<i>{key}:</i>"]
        for i, item in enumerate(value):
            if isinstance(item, (dict, list)):
                parts.append(_format_complex_value(f"[{i}]", item, indent_level + 1))
            else:
                nested_indent = "&nbsp;" * ((indent_level + 1) * 4)
                parts.append(f"{nested_indent}[{i}]: {item}")
        return "<br>".join(parts)

    else:
        return f"{indent}<i>{key}:</i> {value}"


def _format_compound_brunnel_popup(compound: CompoundBrunnelWay) -> str:
    """
    Format a compound brunnel's metadata into HTML for popup display.

    Args:
        compound: CompoundBrunnelWay object

    Returns:
        HTML-formatted string with compound brunnel information
    """
    html_parts = []

    # Header with compound information
    brunnel_type = compound.brunnel_type.value.capitalize()
    component_count = len(compound.components)
    primary_name = compound.get_primary_name()

    html_parts.append(f"<b>Compound {brunnel_type}</b> ({component_count} segments)")

    if primary_name != "unnamed":
        html_parts.append(f"<br><b>Name:</b> {primary_name}")

    # Route span information
    if compound.route_span:
        span = compound.route_span
        html_parts.append(
            f"<br><b>Route Span:</b> {span.start_distance_km:.2f} - {span.end_distance_km:.2f} km "
            f"(length: {span.length_km:.2f} km)"
        )

    # Combined OSM ID
    combined_metadata = compound.get_combined_metadata()
    html_parts.append(f"<br><b>Combined OSM ID:</b> {combined_metadata['id']}")

    # Tag conflicts if any
    if "tag_conflicts" in combined_metadata:
        html_parts.append("<br><b>Tag Conflicts:</b>")
        for key, values in combined_metadata["tag_conflicts"].items():
            values_str = " vs ".join(f"'{v}'" for v in values)
            html_parts.append(f"<br>&nbsp;&nbsp;<i>{key}:</i> {values_str}")

    # Component details
    html_parts.append("<br><br><b>Component Segments:</b>")

    for i, component in enumerate(compound.components):
        html_parts.append(f"<br><br><b>Segment {i+1}:</b>")

        # Component name
        comp_tags = component.metadata.get("tags", {})
        if "name" in comp_tags:
            html_parts.append(f"<br>&nbsp;&nbsp;<b>Name:</b> {comp_tags['name']}")

        # Component OSM ID
        comp_id = component.metadata.get("id", "unknown")
        html_parts.append(f"<br>&nbsp;&nbsp;<b>OSM ID:</b> {comp_id}")

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
                html_parts.append(f"<br>&nbsp;&nbsp;&nbsp;&nbsp;<i>{key}:</i> {value}")

    return "".join(html_parts)


def _format_regular_brunnel_popup(brunnel: BrunnelWay) -> str:
    """
    Format a regular brunnel's metadata into HTML for popup display.

    Args:
        brunnel: BrunnelWay object

    Returns:
        HTML-formatted string with metadata
    """
    html_parts = []
    tags = brunnel.metadata.get("tags", {})

    # Add name most prominently if present
    if "name" in tags:
        html_parts.append(f"<b>{tags['name']}</b>")

    # Add alt_name next if present
    if "alt_name" in tags:
        html_parts.append(f"<br><b>AKA:</b> {tags['alt_name']}")

    # Add OSM ID
    osm_id = brunnel.metadata.get("id", "unknown")
    html_parts.append(f"<br><b>OSM ID:</b> {osm_id}")

    # Add remaining OSM tags (excluding name and alt_name which we already showed)
    remaining_tags = {k: v for k, v in tags.items() if k not in ["name", "alt_name"]}
    if remaining_tags:
        html_parts.append("<br><b>Tags:</b>")
        for key, value in sorted(remaining_tags.items()):
            html_parts.append(f"<br>&nbsp;&nbsp;<i>{key}:</i> {value}")

    # Add other metadata (excluding tags and id which we already handled, geometry, which is very long, and type, which is always "way")
    other_data = {
        k: v
        for k, v in brunnel.metadata.items()
        if k not in ["tags", "id", "geometry", "type"]
    }
    if other_data:
        html_parts.append("<br><b>Other:</b>")
        for key, value in sorted(other_data.items()):
            # Handle nested dictionaries or lists
            if isinstance(value, (dict, list)):
                # Use structured formatting for nodes and bounds
                if key in ["nodes", "bounds"]:
                    formatted_value = _format_complex_value(key, value, 0)
                    # Add proper indentation for the "Other:" section
                    indented_lines = []
                    for line in formatted_value.split("<br>"):
                        if line.strip():  # Skip empty lines
                            indented_lines.append(f"&nbsp;&nbsp;{line}")
                    html_parts.append("<br>" + "<br>".join(indented_lines))
                else:
                    # Keep truncation for other long nested data
                    value_str = str(value)
                    if len(value_str) > 50:
                        value_str = value_str[:47] + "..."
                    html_parts.append(f"<br>&nbsp;&nbsp;<i>{key}:</i> {value_str}")
            else:
                value_str = str(value)
                html_parts.append(f"<br>&nbsp;&nbsp;<i>{key}:</i> {value_str}")

    return "".join(html_parts)


def _get_brunnel_coordinates(brunnel: BrunnelLike) -> List[List[float]]:
    """
    Get coordinates from a brunnel (regular or compound).

    Args:
        brunnel: BrunnelWay or CompoundBrunnelWay object

    Returns:
        List of [latitude, longitude] pairs
    """
    if isinstance(brunnel, CompoundBrunnelWay):
        coords = brunnel.coordinate_list
    else:
        coords = brunnel.coords

    return [[pos.latitude, pos.longitude] for pos in coords]


def _get_brunnel_type(brunnel: BrunnelLike) -> BrunnelType:
    """Get the brunnel type from a brunnel object."""
    return brunnel.brunnel_type


def _is_brunnel_contained(brunnel: BrunnelLike) -> bool:
    """Check if a brunnel is contained in the route."""
    return brunnel.contained_in_route


def _get_brunnel_filter_reason(brunnel: BrunnelLike) -> FilterReason:
    """Get the filter reason from a brunnel object."""
    return brunnel.filter_reason


def _get_brunnel_route_span(brunnel: BrunnelLike):
    """Get the route span from a brunnel object."""
    return brunnel.route_span


def create_route_map(
    route: Route,
    output_filename: str,
    brunnels: List[BrunnelLike],
    buffer_km: float,
) -> None:
    """
    Create an interactive map showing the route and nearby bridges/tunnels, save as HTML.

    Args:
        route: Route object representing the route
        output_filename: Path where HTML map file should be saved
        brunnels: List of BrunnelWay or CompoundBrunnelWay objects to display on map
        buffer_km: Buffer distance in kilometers for map bounds (default: 1.0)

    Raises:
        ValueError: If route is empty
    """
    if not route:
        raise ValueError("Cannot create map for empty route")

    # Calculate buffered bounding box using existing function
    south, west, north, east = route.get_bbox(buffer_km)

    center_lat = (south + north) / 2
    center_lon = (west + east) / 2

    logger.debug(f"Creating map centered at ({center_lat:.4f}, {center_lon:.4f})")

    # Create map with initial center (zoom will be set by fit_bounds)
    route_map = folium.Map(location=[center_lat, center_lon], tiles="CartoDB positron")

    # Convert route to coordinate pairs for folium
    coordinates = [[pos.latitude, pos.longitude] for pos in route]

    # Add route as polyline
    folium.PolyLine(
        coordinates, color="red", weight=2, opacity=0.6, popup="GPX Route", z_index=1
    ).add_to(route_map)

    # Add start and end markers
    folium.Marker(
        [route[0].latitude, route[0].longitude],
        popup="Start",
        icon=folium.Icon(color="green", icon="play"),
    ).add_to(route_map)

    folium.Marker(
        [route[-1].latitude, route[-1].longitude],
        popup="End",
        icon=folium.Icon(color="red", icon="stop"),
    ).add_to(route_map)

    # Count brunnels by type and containment status
    bridge_count = 0
    tunnel_count = 0
    contained_bridge_count = 0
    contained_tunnel_count = 0

    for brunnel in brunnels:
        brunnel_coords = _get_brunnel_coordinates(brunnel)
        if not brunnel_coords:
            continue

        brunnel_type = _get_brunnel_type(brunnel)
        contained = _is_brunnel_contained(brunnel)
        filter_reason = _get_brunnel_filter_reason(brunnel)
        route_span = _get_brunnel_route_span(brunnel)

        # Determine color and opacity based on containment status and filtering
        if contained:
            opacity = 0.9
            weight = 4
            if brunnel_type == BrunnelType.BRIDGE:
                color = "blue"
                contained_bridge_count += 1
            else:  # TUNNEL
                color = "brown"
                contained_tunnel_count += 1
        else:
            # Use muted colors for filtered or non-contained brunnels
            opacity = 0.3
            weight = 2
            if brunnel_type == BrunnelType.BRIDGE:
                color = "lightsteelblue"  # grey-blue for bridges
            else:  # TUNNEL
                color = "rosybrown"  # grey-brown for tunnels

        # Count all brunnels
        if brunnel_type == BrunnelType.BRIDGE:
            bridge_count += 1
        else:
            tunnel_count += 1

        # Create popup text with full metadata
        if contained:
            if route_span:
                status = (
                    f"{route_span.start_distance_km:.2f} - {route_span.end_distance_km:.2f} km; "
                    f"length: {route_span.length_km:.2f} km"
                )
            else:
                status = "contained in route buffer"
        elif filter_reason == FilterReason.NOT_CONTAINED:
            status = "not contained in route buffer"
        else:
            status = f"filtered: {filter_reason}"

        popup_header = f"<b>{brunnel_type.value.capitalize()}</b> ({status})<br>"

        # Format metadata based on brunnel type
        if isinstance(brunnel, CompoundBrunnelWay):
            metadata_html = _format_compound_brunnel_popup(brunnel)
        else:
            metadata_html = _format_regular_brunnel_popup(brunnel)

        popup_text = popup_header + metadata_html

        # Style and add brunnel based on type
        if brunnel_type == BrunnelType.TUNNEL:
            # Use dashed line for ALL tunnels (both contained and non-contained)
            folium.PolyLine(
                brunnel_coords,
                color=color,
                weight=weight,
                opacity=opacity,
                dash_array="5, 5",
                popup=folium.Popup(
                    popup_text, max_width=400
                ),  # Wider for compound brunnels
                z_index=2,  # Ensure tunnels are above route
            ).add_to(route_map)
        else:
            # Solid line for all bridges
            folium.PolyLine(
                brunnel_coords,
                color=color,
                weight=weight,
                opacity=opacity,
                popup=folium.Popup(
                    popup_text, max_width=400
                ),  # Wider for compound brunnels
                z_index=2,  # Ensure bridges are above route
            ).add_to(route_map)

    # Fit map bounds to buffered route area
    bounds = [[south, west], [north, east]]  # Southwest corner  # Northeast corner
    route_map.fit_bounds(bounds)

    # Add legend as HTML overlay by post-processing the saved file
    legend_html = f"""
    <div style='position: fixed; bottom: 50px; left: 50px; width: 220px; height: 170px; 
                background-color: white; border: 2px solid grey; z-index: 9999; 
                font-size: 14px; padding: 10px; font-family: Arial, sans-serif;'>
        <b>Legend</b><br>
        <span style='color: red; font-weight: bold;'>—</span> GPX Route<br>
        <span style='color: blue; font-weight: bold;'>—</span> Included Bridges ({contained_bridge_count})<br>
        <span style='color: brown; font-weight: bold;'>- -</span> Included Tunnels ({contained_tunnel_count})<br>
        <span style='color: lightsteelblue; font-weight: bold;'>—</span> Excluded Bridges ({bridge_count - contained_bridge_count})<br>
        <span style='color: rosybrown; font-weight: bold;'>- -</span> Excluded Tunnels ({tunnel_count - contained_tunnel_count})
    </div>
    """

    # Save map first
    route_map.save(output_filename)

    # Read the saved HTML file and inject legend
    with open(output_filename, "r", encoding="utf-8") as f:
        html_content = f.read()

    # Insert legend before closing body tag
    html_content = html_content.replace("</body>", legend_html + "</body>")

    # Write back the modified HTML
    with open(output_filename, "w", encoding="utf-8") as f:
        f.write(html_content)
    logger.debug(
        f"Map saved to {output_filename} with {contained_bridge_count}/{bridge_count} bridges and {contained_tunnel_count}/{tunnel_count} tunnels contained in route buffer"
    )
