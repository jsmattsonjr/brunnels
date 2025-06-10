from dataclasses import dataclass


@dataclass
class BrunnelsConfig:
    """Configuration for the brunnels CLI."""

    bbox_buffer: float = 10.0
    route_buffer: float = 3.0
    bearing_tolerance: float = 20.0
    no_overlap_filtering: bool = False
    log_level: str = "INFO"
    metrics: bool = False
