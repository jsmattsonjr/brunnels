#!/usr/bin/env python3
"""
Route visualization using folium maps.
"""

from typing import Dict
import collections
import logging
import argparse
import folium
from folium.template import Template

from .brunnel import Brunnel, BrunnelType, FilterReason
from .route import Route

logger = logging.getLogger(__name__)


class BrunnelLegend(folium.MacroElement):
    """Custom legend for brunnel visualization with dynamic counts."""

    def __init__(
        self, bridge_count, tunnel_count, contained_bridge_count, contained_tunnel_count
    ):
        super().__init__()
        self.bridge_count = bridge_count
        self.tunnel_count = tunnel_count
        self.contained_bridge_count = contained_bridge_count
        self.contained_tunnel_count = contained_tunnel_count

        # Use folium's template string approach
        self._template = Template(
            """
        {% macro html(this, kwargs) %}
        <div id="brunnel-legend" style="
            position: fixed;
            bottom: 50px;
            left: 50px;
            width: 230px;
            min-height: 140px;
            max-height: 250px;
            background-color: white;
            border: 2px solid grey;
            z-index: 9999;
            font-size: 13px;
            padding: 12px;
            font-family: Arial, sans-serif;
            border-radius: 5px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.2);
            overflow: hidden;
            box-sizing: border-box;
        ">
            <b>Legend</b><br>
            <div style="margin: 4px 0; line-height: 1.3;">
                <span style="color: red; font-weight: bold; font-size: 16px;">—</span>
                GPX Route
            </div>
            <div style="margin: 4px 0; line-height: 1.3;">
                <span style="color: blue; font-weight: bold; font-size: 16px;">—</span>
                Included Bridges ({{ this.contained_bridge_count }})
            </div>
            <div style="margin: 4px 0; line-height: 1.3;">
                <span style="color: brown; font-weight: bold; font-size: 16px; letter-spacing: 2px;">- -</span>
                Included Tunnels ({{ this.contained_tunnel_count }})
            </div>
            <div style="margin: 4px 0; line-height: 1.3;">
                <span style="color: lightsteelblue; font-weight: bold; font-size: 16px;">—</span>
                Excluded Bridges ({{ this.bridge_count - this.contained_bridge_count }})
            </div>
            <div style="margin: 4px 0; line-height: 1.3;">
                <span style="color: rosybrown; font-weight: bold; font-size: 16px; letter-spacing: 2px;">- -</span>
                Excluded Tunnels ({{ this.tunnel_count - this.contained_tunnel_count }})
            </div>
        </div>
        {% endmacro %}
        """
        )


def create_route_map(
    route: Route,
    output_filename: str,
    brunnels: Dict[str, Brunnel],
    args: argparse.Namespace,
) -> None:
    """
    Create an interactive map showing the route and nearby bridges/tunnels, save as HTML.

    Args:
        route: Route object representing the route
        output_filename: Path where HTML map file should be saved
        brunnels: Dictionary of Brunnel objects to display on map
        args: argparse.Namespace object containing settings like buffer and metrics flag

    Raises:
        ValueError: If route is empty
    """
    if not route:
        raise ValueError("Cannot create map for empty route")

    # Calculate buffered bounding box using existing function
    south, west, north, east = route.get_bbox(args.bbox_buffer)

    center_lat = (south + north) / 2
    center_lon = (west + east) / 2

    logger.debug(f"Creating map centered at ({center_lat:.4f}, {center_lon:.4f})")

    # Initialize map (CartoDB positron will be the default base, but also explicitly added for control)
    route_map = folium.Map(
        location=[center_lat, center_lon],
        tiles=None,
    )

    # Add Standard layer (CartoDB positron)
    folium.TileLayer(
        tiles="CartoDB positron",
        attr=(
            "&copy; <a href='https://www.openstreetmap.org/copyright'>OpenStreetMap</a> "
            "contributors &copy; <a href='https://carto.com/attributions'>CARTO</a>"
        ),
        name="Standard",
        control=True,
        show=True,  # Show by default
    ).add_to(route_map)

    # Add Satellite layer (Esri World Imagery)
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr=(
            "Tiles &copy; Esri &mdash; Source: Esri, i-cubed, USDA, USGS, AEX, GeoEye, "
            "Getmapping, Aerogrid, IGN, IGP, UPR-EGP, and the GIS User Community"
        ),
        name="Satellite",
        control=True,
        show=False,  # Initially hidden
    ).add_to(route_map)

    # Add LayerControl
    folium.LayerControl().add_to(route_map)

    # Convert route to coordinate pairs for folium using the new method
    coordinates = [[pos.latitude, pos.longitude] for pos in route.coordinate_list]

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
    compound_count = 0
    individual_count = 0
    filter_reason_counts: Dict[FilterReason, int] = collections.Counter()

    for brunnel in brunnels.values():
        brunnel_coords = [[pos.latitude, pos.longitude] for pos in brunnel.coordinate_list]
        if not brunnel_coords:
            continue

        brunnel_type = brunnel.brunnel_type
        filter_reason = brunnel.filter_reason
        route_span = brunnel.get_route_span()

        if filter_reason != FilterReason.NONE:
            filter_reason_counts[filter_reason] += 1

        # Determine color and opacity based on containment status and filtering
        if filter_reason == FilterReason.NONE:
            opacity = 0.9
            weight = 4
            if brunnel_type == BrunnelType.BRIDGE:
                color = "blue"
                if brunnel.is_representative():
                    contained_bridge_count += 1
            else:  # TUNNEL
                color = "brown"
                if brunnel.is_representative():
                    contained_tunnel_count += 1
        else:
            # Use muted colors for filtered or non-contained brunnels
            opacity = 0.3
            weight = 2
            if brunnel_type == BrunnelType.BRIDGE:
                color = "lightsteelblue"  # grey-blue for bridges
            else:  # TUNNEL
                color = "rosybrown"  # grey-brown for tunnels

        # Count all representative brunnels
        if brunnel.is_representative():
            if brunnel_type == BrunnelType.BRIDGE:
                bridge_count += 1
            else:
                tunnel_count += 1

            if filter_reason == FilterReason.NONE:
                if brunnel.compound_group is not None:
                    compound_count += 1
                else:
                    individual_count += 1

        # Create popup text with full metadata
        if filter_reason == FilterReason.NONE:
            if route_span:
                status = (
                    f"{route_span.start_distance:.2f} - {route_span.end_distance:.2f} km; "
                    f"length: {route_span.end_distance - route_span.start_distance:.2f} km"
                )
            else:
                status = "contained in route buffer"
        elif filter_reason == FilterReason.NOT_CONTAINED:
            status = "not contained in route buffer"
        else:
            status = f"filtered: {filter_reason}"

        popup_header = f"<b>{brunnel_type.value.capitalize()}</b> ({status})<br>"

        metadata_html = brunnel.to_html()
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

    # Add legend with dynamic counts
    legend = BrunnelLegend(
        bridge_count,
        tunnel_count,
        contained_bridge_count,
        contained_tunnel_count,
    )
    route_map.add_child(legend)

    # Fit map bounds to buffered route area
    bounds = [[south, west], [north, east]]  # Southwest corner  # Northeast corner
    route_map.fit_bounds(bounds)

    route_map.save(output_filename)

    logger.debug(
        f"Map saved to {output_filename} with {contained_bridge_count}/{bridge_count} bridges and {contained_tunnel_count}/{tunnel_count} tunnels contained in route buffer"
    )

    if args.metrics:
        # Log detailed filtering metrics
        logger.debug("=== BRUNNELS_METRICS ===")
        logger.debug(f"total_brunnels_found={len(brunnels)}")
        logger.debug(f"total_bridges_found={bridge_count}")
        logger.debug(f"total_tunnels_found={tunnel_count}")

        for reason, count in filter_reason_counts.items():
            logger.debug((f"filtered_reason[{reason.value}]={count}"))

        logger.debug(f"contained_bridges={contained_bridge_count}")
        logger.debug(f"contained_tunnels={contained_tunnel_count}")
        logger.debug(f"final_included_individual={individual_count}")
        logger.debug(f"final_included_compound={compound_count}")
        logger.debug(f"final_included_total={individual_count + compound_count}")
        logger.debug("=== END_BRUNNELS_METRICS ===")
