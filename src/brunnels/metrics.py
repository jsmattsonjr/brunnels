"""
Module for collecting and logging metrics related to brunnels.
"""

import argparse
import collections
import logging
from typing import Dict, NamedTuple
from .brunnel import Brunnel, BrunnelType, ExclusionReason

logger = logging.getLogger(__name__)


class BrunnelMetrics(NamedTuple):
    """Container for brunnel metrics data."""

    bridge_counts: Dict[str, int]
    tunnel_counts: Dict[str, int]


def collect_metrics(brunnels: Dict[str, Brunnel]) -> BrunnelMetrics:
    """
    Collect metrics from brunnels before creating the route map.

    Args:
        brunnels: Dictionary of Brunnel objects to analyze

    Returns:
        BrunnelMetrics containing all collected metrics
    """
    # Initialize count dictionaries
    bridge_counts: Dict[str, int] = collections.defaultdict(int)
    tunnel_counts: Dict[str, int] = collections.defaultdict(int)
    total_individual = 0
    total_compound = 0

    for brunnel in brunnels.values():
        brunnel_type = brunnel.brunnel_type
        exclusion_reason = brunnel.exclusion_reason

        # Count all representative brunnels
        if brunnel.is_representative():
            counts_dict = (
                bridge_counts if brunnel_type == BrunnelType.BRIDGE else tunnel_counts
            )

            # Total count
            counts_dict["total"] += 1

            # Contained/included count
            if exclusion_reason == ExclusionReason.NONE:
                counts_dict["contained"] += 1

                # Individual vs compound count
                if brunnel.compound_group is not None:
                    counts_dict["compound"] += 1
                    total_compound += 1
                else:
                    counts_dict["individual"] += 1
                    total_individual += 1
            else:
                # Exclusion reason counts
                counts_dict[exclusion_reason.value] += 1

    return BrunnelMetrics(
        bridge_counts=dict(bridge_counts),
        tunnel_counts=dict(tunnel_counts),
    )


def log_metrics(
    brunnels: Dict[str, Brunnel], metrics: BrunnelMetrics, args: argparse.Namespace
) -> None:
    """
    Log detailed metrics after creating the route map.

    Args:
        brunnels: Dictionary of Brunnel objects (for total count)
        metrics: BrunnelMetrics containing collected metrics
        args: argparse.Namespace object containing settings like metrics flag
    """
    if not args.metrics:
        return

    # Log detailed metrics
    logger.debug("=== BRUNNELS_METRICS ===")
    logger.debug(f"total_brunnels_found={len(brunnels)}")
    logger.debug(f"total_bridges_found={metrics.bridge_counts.get('total', 0)}")
    logger.debug(f"total_tunnels_found={metrics.tunnel_counts.get('total', 0)}")

    # Log exclusion reasons for bridges
    for key, count in metrics.bridge_counts.items():
        if key not in ["total", "contained", "individual", "compound"] and count > 0:
            logger.debug(f"excluded_reason[{key}][bridge]={count}")

    # Log exclusion reasons for tunnels
    for key, count in metrics.tunnel_counts.items():
        if key not in ["total", "contained", "individual", "compound"] and count > 0:
            logger.debug(f"excluded_reason[{key}][tunnel]={count}")

    logger.debug(f"contained_bridges={metrics.bridge_counts.get('contained', 0)}")
    logger.debug(f"contained_tunnels={metrics.tunnel_counts.get('contained', 0)}")
    logger.debug(
        f"final_included_individual={metrics.bridge_counts.get('individual', 0) + metrics.tunnel_counts.get('individual', 0)}"
    )
    logger.debug(
        f"final_included_compound={metrics.bridge_counts.get('compound', 0) + metrics.tunnel_counts.get('compound', 0)}"
    )
    logger.debug(
        f"final_included_total={metrics.bridge_counts.get('contained', 0) + metrics.tunnel_counts.get('contained', 0)}"
    )
    logger.debug("=== END_BRUNNELS_METRICS ===")
