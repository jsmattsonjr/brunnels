"""
Module for collecting and logging metrics related to brunnels.
"""

import argparse
import collections
import sys
from typing import Dict, NamedTuple
from .brunnel import Brunnel, BrunnelType, ExclusionReason


def eprint(*args, **kwargs):
    """
    Prints the given arguments to standard error (stderr).
    Accepts the same arguments as the built-in print() function.
    """
    print(*args, file=sys.stderr, **kwargs)


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
    Output detailed metrics after creating the route map directly to stderr.

    Args:
        brunnels: Dictionary of Brunnel objects (for total count)
        metrics: BrunnelMetrics containing collected metrics
        args: argparse.Namespace object containing settings like metrics flag
    """
    if not args.metrics:
        return

    # Output detailed metrics directly to stderr
    eprint("=== BRUNNELS_METRICS ===")
    eprint(f"total_brunnels_found={len(brunnels)}")
    eprint(f"total_bridges_found={metrics.bridge_counts.get('total', 0)}")
    eprint(f"total_tunnels_found={metrics.tunnel_counts.get('total', 0)}")

    # Output exclusion reasons for bridges
    for key, count in metrics.bridge_counts.items():
        if key not in ["total", "contained", "individual", "compound"] and count > 0:
            eprint(f"excluded_reason[{key}][bridge]={count}")

    # Output exclusion reasons for tunnels
    for key, count in metrics.tunnel_counts.items():
        if key not in ["total", "contained", "individual", "compound"] and count > 0:
            eprint(f"excluded_reason[{key}][tunnel]={count}")

    eprint(f"contained_bridges={metrics.bridge_counts.get('contained', 0)}")
    eprint(f"contained_tunnels={metrics.tunnel_counts.get('contained', 0)}")
    eprint(
        f"final_included_individual={metrics.bridge_counts.get('individual', 0) + metrics.tunnel_counts.get('individual', 0)}"
    )
    eprint(
        f"final_included_compound={metrics.bridge_counts.get('compound', 0) + metrics.tunnel_counts.get('compound', 0)}"
    )
    eprint(
        f"final_included_total={metrics.bridge_counts.get('contained', 0) + metrics.tunnel_counts.get('contained', 0)}"
    )
    eprint("=== END_BRUNNELS_METRICS ===")
