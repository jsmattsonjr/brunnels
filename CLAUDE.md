# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## About This Project

Brunnels is a Python CLI tool that analyzes GPX routes to identify bridges and tunnels along the path. It uses OpenStreetMap data via the Overpass API and generates interactive HTML maps with sophisticated filtering and visualization.

## Development Commands

### Installation and Setup
```bash
# Development installation
pip install -e ".[dev]"

# Install dependencies only (no package installation)
pip install gpxpy>=1.4.2,<2.0 shapely>=1.8.0,<3.0 pyproj>=3.2.0,<4.0 folium>=0.12.0,<1.0 requests>=2.25.0,<3.0
```

### Running the Application
```bash
# If installed
brunnels your_route.gpx

# From source (preferred for development)
python3 -m brunnels.cli your_route.gpx
```

### Testing
```bash
# Run all tests; may take up to 10 minutes
pytest

# Run single test
pytest tests/test_integration.py::TestIntegration::test_specific_method
```

### Code Quality
```bash
# Format code
black src/brunnels/

# Type checking
mypy src/brunnels/

# Linting
flake8 src/brunnels/
```

## Architecture Overview

The codebase follows a modular architecture with clear separation of concerns:

### Core Modules

- **`cli.py`**: Main entry point that orchestrates the workflow (GPX loading → Route creation → Brunnel discovery → Filtering → Visualization)
- **`route.py`**: Core `Route` class that manages GPX routes, coordinates brunnel discovery via Overpass API, and performs geometric filtering operations
- **`brunnel.py`**: Data structures for bridges/tunnels including `Brunnel` class with containment analysis, bearing alignment, and compound brunnel support
- **`geometry.py`**: Geometric utilities using Shapely and pyproj for accurate coordinate transformations, bearing calculations, and spatial operations
- **`overpass.py`**: OpenStreetMap Overpass API interface with retry logic and configurable filtering
- **`visualization.py`**: Interactive map generation using Folium with color-coded brunnel display and custom legends
- **`metrics.py`**: Statistical analysis and structured logging of brunnel processing results
- **`file_utils.py`**: File operations including automatic output filename generation with conflict resolution

### Key Dependencies
- Route → Brunnel: Creates and manages brunnel collections
- Route → Overpass: Fetches OpenStreetMap data
- Route/Brunnel → Geometry: Uses projections and spatial calculations
- Visualization → Route/Brunnel: Renders maps from data structures

### Data Flow
1. GPX file parsed into Route object
2. Route queries Overpass API for bridge/tunnel data in bounding box
3. Raw OSM data converted to Brunnel objects
4. Multiple filtering stages: containment, bearing alignment, overlap exclusion
5. Filtered brunnels rendered to interactive HTML map
6. Optional metrics collection and logging

## Important Implementation Details

### Coordinate Systems
- Uses WGS84 decimal degrees for input/storage
- Creates custom Transverse Mercator projections for accurate distance calculations
- Handles worldwide routes (excludes polar regions and antimeridian crossings)

### Geometric Analysis
- Route buffering accounts for GPS accuracy (default 3m buffer)
- Bearing alignment checks prevent inclusion of perpendicular infrastructure
- Overlap exclusion keeps nearest brunnel among overlapping route spans
- Adjacent brunnel merging combines fragmented OSM ways into continuous segments

### Filtering Pipeline
1. **Cycling relevance**: Excludes `bicycle=no`, active railways, pure waterways
2. **Containment**: Only includes brunnels intersecting buffered route geometry
3. **Bearing alignment**: Filters based on compass direction alignment (±20° default)
4. **Overlap exclusion**: Removes overlapping brunnels, keeping nearest to route

### Testing
- Integration tests use real GPX files in `tests/fixtures/`
- Test files include various route types (urban, rural, international)
- Tests validate end-to-end functionality including API calls and map generation

### Git Commits
- Include Jim Mattson <jsmattsonjr@gmail.com> as co-author.