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

    bridge_count: int
    tunnel_count: int
    contained_bridge_count: int
    contained_tunnel_count: int
    individual_count: int
    compound_count: int
    exclusion_reason_counts: Dict[ExclusionReason, int]


def collect_metrics(brunnels: Dict[str, Brunnel]) -> BrunnelMetrics:
    """
    Collect metrics from brunnels before creating the route map.

    Args:
        brunnels: Dictionary of Brunnel objects to analyze

    Returns:
        BrunnelMetrics containing all collected metrics
    """
    bridge_count = 0
    tunnel_count = 0
    contained_bridge_count = 0
    contained_tunnel_count = 0
    compound_count = 0
    individual_count = 0
    exclusion_reason_counts: Dict[ExclusionReason, int] = collections.Counter()

    for brunnel in brunnels.values():
        brunnel_type = brunnel.brunnel_type
        exclusion_reason = brunnel.exclusion_reason

        if exclusion_reason != ExclusionReason.NONE:
            exclusion_reason_counts[exclusion_reason] += 1

        # Count all representative brunnels
        if brunnel.is_representative():
            if brunnel_type == BrunnelType.BRIDGE:
                bridge_count += 1
                if exclusion_reason == ExclusionReason.NONE:
                    contained_bridge_count += 1
            else:  # TUNNEL
                tunnel_count += 1
                if exclusion_reason == ExclusionReason.NONE:
                    contained_tunnel_count += 1

            if exclusion_reason == ExclusionReason.NONE:
                if brunnel.compound_group is not None:
                    compound_count += 1
                else:
                    individual_count += 1

    return BrunnelMetrics(
        bridge_count=bridge_count,
        tunnel_count=tunnel_count,
        contained_bridge_count=contained_bridge_count,
        contained_tunnel_count=contained_tunnel_count,
        individual_count=individual_count,
        compound_count=compound_count,
        exclusion_reason_counts=exclusion_reason_counts,
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

    # Log detailed exclusion metrics
    logger.debug("=== BRUNNELS_METRICS ===")
    logger.debug(f"total_brunnels_found={len(brunnels)}")
    logger.debug(f"total_bridges_found={metrics.bridge_count}")
    logger.debug(f"total_tunnels_found={metrics.tunnel_count}")

    for reason, count in metrics.exclusion_reason_counts.items():
        logger.debug(f"excluded_reason[{reason.value}]={count}")

    logger.debug(f"contained_bridges={metrics.contained_bridge_count}")
    logger.debug(f"contained_tunnels={metrics.contained_tunnel_count}")
    logger.debug(f"final_included_individual={metrics.individual_count}")
    logger.debug(f"final_included_compound={metrics.compound_count}")
    logger.debug(
        f"final_included_total={metrics.individual_count + metrics.compound_count}"
    )
    logger.debug("=== END_BRUNNELS_METRICS ===")
