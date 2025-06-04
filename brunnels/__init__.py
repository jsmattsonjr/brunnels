#!/usr/bin/env python3
"""
Brunnels - A GPX route analysis tool for bridges and tunnels.

This package provides tools to identify bridges and tunnels along GPS routes
and visualize them on interactive maps using OpenStreetMap data.
"""
import importlib.metadata

__version__ = importlib.metadata.version('brunnels')
__author__ = "Jim Mattson"
__email__ = "jsmattsonjr@gmail.com"

# Import main classes for public API
from .brunnel import Brunnel, BrunnelType, FilterReason, RouteSpan
from .brunnel_way import BrunnelWay
from .compound_brunnel_way import CompoundBrunnelWay
from .route import Route, RouteValidationError
from .geometry import Position

__all__ = [
    "Brunnel",
    "BrunnelType",
    "FilterReason",
    "RouteSpan",
    "BrunnelWay",
    "CompoundBrunnelWay",
    "Route",
    "RouteValidationError",
    "Position",
]
