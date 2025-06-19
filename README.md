# Brunnels

A GPX route analysis tool that identifies bridges and tunnels along your route and visualizes them on an interactive map.

## What is a Brunnel?

"Brunnel" is a portmanteau of "bridge" and "tunnel" used in this tool to refer to both types of infrastructure collectively. This term is commonly used on the Biketerra Discord server.

## Features

- **GPX Route Processing**: Parse GPX files containing GPS tracks from cycling computers, fitness apps, or route planning tools
- **OpenStreetMap Integration**: Query real bridge and tunnel data from OpenStreetMap via the Overpass API
- **Smart Exclusion**: Exclude bridges/tunnels based on cycling relevance (bicycle access, infrastructure type)
- **Containment Analysis**: Identify which bridges/tunnels your route actually crosses vs. those merely nearby
- **Bearing Alignment**: Exclude bridges/tunnels that aren't aligned with your route direction (configurable tolerance)
- **Interactive Visualization**: Generate beautiful HTML maps with route and brunnel overlay
- **Detailed Metadata**: View comprehensive OpenStreetMap tags and properties for each brunnel
- **Adjacent Way Merging**: Automatically combines adjacent bridge/tunnel ways that share OSM nodes into single continuous brunnels

## Installation

### Requirements

- Python >=3.9
- Internet connection (for OpenStreetMap data queries)

### Install from GitHub

```bash
pip install git+https://github.com/jsmattsonjr/brunnels.git
```

### Development Installation

```bash
git clone https://github.com/jsmattsonjr/brunnels.git
cd brunnels
pip install -e .
```

### Run from Source (No Installation)

If you prefer not to install the package, you can run it directly from the cloned repository:

```bash
git clone https://github.com/jsmattsonjr/brunnels.git
cd brunnels
# Install dependencies only
pip install gpxpy>=1.4.2,<2.0 shapely>=1.8.0,<3.0 pyproj>=3.2.0,<4.0 folium>=0.12.0,<1.0 requests>=2.25.0,<3.0
# Run directly from source
python3 -m brunnels.cli your_route.gpx
```


## Usage

### Basic Usage

**If installed via pip:**
```bash
brunnels your_route.gpx
```

**If running from source:**
```bash
python3 -m brunnels.cli your_route.gpx
```

This will:
1. Parse your GPX file
2. Find all bridges and tunnels in an area extending 10m beyond your route's bounding box
3. Exclude brunnels based on cycling relevance and bearing alignment with your route
4. Generate an interactive map with a filename based on your input file (e.g., `route.gpx` → `route map.html`)
5. Automatically open the map in your default browser

If the output file already exists, the tool will automatically try numbered variations (e.g., `route map (1).html`, `route map (2).html`) to avoid overwriting existing files.

### Advanced Options

**If installed via pip:**
```bash
brunnels route.gpx \
  --output my_map.html \
  --bbox-buffer 0.5 \
  --route-buffer 5.0 \
  --bearing-tolerance 15.0 \
  --log-level DEBUG
```

**If running from source:**
```bash
python3 -m brunnels.cli route.gpx \
  --output my_map.html \
  --bbox-buffer 0.5 \
  --route-buffer 5.0 \
  --bearing-tolerance 15.0 \
  --log-level DEBUG
```

### Options

- `--output FILE`: Specify output HTML filename (default: auto-generated based on input filename)
- `--bbox-buffer DISTANCE`: Search radius around route in meters (default: 10m)
- `--route-buffer DISTANCE`: Route containment buffer in meters (default: 3.0m)
- `--bearing-tolerance DEGREES`: Bearing alignment tolerance in degrees (default: 20.0°)
- `--no-overlap-exclusion`: Disable exclusion of overlapping brunnels (keep all overlapping brunnels)
- `--include-bicycle-no`: Include ways tagged `bicycle=no` in the Overpass query.
- `--include-waterways`: Include ways tagged as `waterway` in the Overpass query.
- `--include-active-railways`: Include ways tagged as `railway` with values other than `abandoned` in the Overpass query.
- `--log-level LEVEL`: Set logging verbosity (DEBUG, INFO, WARNING, ERROR, CRITICAL) (default: WARNING)
- `--metrics`: Output detailed structured metrics about the processing of brunnels. Examples include: total brunnels found, total bridges and tunnels found, counts of brunnels excluded by different reasons, and counts of finally included brunnels (individual, compound, total). Note that this option also sets the log level to `DEBUG`.
- `--version`: Show program's version number and exit.
- `--no-open`: Don't automatically open the map in browser

## Output Files

### Automatic Filename Generation

By default, the tool generates output filenames based on your input file:

- `my_route.gpx` → `my_route map.html`
- `Sunday Ride.GPX` → `Sunday Ride map.html`
- `track.tcx` → `track.tcx map.html` (if you somehow use non-GPX files)

If the output file already exists, numbered versions are automatically tried:
- `my_route map.html` (if this exists, try...)
- `my_route map (1).html` (if this exists, try...)
- `my_route map (2).html` (and so on...)

## Understanding the Output

### Interactive Map

The generated HTML map includes:

- **Blue line**: Your GPX route
- **Red lines**: Bridges that your route crosses
- **Purple lines**: Tunnels that your route passes through
- **Green marker**: Route start
- **Red marker**: Route end

### Legend

- Numbers in parentheses show counts
- Click on any brunnel for detailed OpenStreetMap metadata
- Contained brunnels show route span information (start/end distances, length)

### Exclusion

The tool applies smart exclusion criteria for cycling routes:

- **Keeps**: Bridges/tunnels with bicycle access allowed or `highway=cycleway`
- **Excludes**: Infrastructure marked `bicycle=no`, pure waterways, active railways
- **Bearing alignment**: Excludes brunnels whose direction doesn't align with your route (±20° tolerance by default)

### Bearing Alignment

The tool checks if bridges and tunnels are aligned with your route direction by:

1. Finding the closest segments between the brunnel and your route
2. Calculating bearing (compass direction) for both segments
3. Checking if they're aligned within tolerance (same or opposite direction)
4. Excludes perpendicular or oddly-angled infrastructure that you don't actually cross

This prevents including nearby infrastructure that intersects your route buffer but runs perpendicular to your actual path.

### Overlap Exclusion

The tool automatically excludes overlapping brunnels to reduce visual clutter when multiple parallel bridges or tunnels span similar portions of your route. When brunnels have overlapping route spans:

Distance calculation: The tool calculates the average distance from each brunnel to your route
Nearest selection: Only the closest brunnel in each overlapping group is kept
Excluded brunnels: Non-nearest brunnels are excluded from the map display

This feature can be disabled with `--no-overlap-exclusion` if you want to include all detected infrastructure.

### Merging

The tool automatically merges adjacent brunnels of the same type (bridge or tunnel) that share OpenStreetMap nodes. This combines fragmented infrastructure into continuous segments for cleaner visualization. The merging process:

- Detects shared nodes between adjacent segments along your route
- Handles directional concatenation of coordinates and metadata
- Resolves tag conflicts by keeping the first brunnel's values
- Updates route spans to cover the full merged length
- Removes duplicate segments from the final output

## Technical Details

### Coordinate System
- Uses WGS84 decimal degrees (standard GPS coordinates)
- Handles routes worldwide (excludes polar regions and antimeridian crossings)

### Data Sources
- Brunnel data from OpenStreetMap via Overpass API
- Respects OSM usage policies with reasonable request timeouts
- Processes OSM tags for cycling relevance and infrastructure type

### Geometric Analysis
- Uses Shapely for precise geometric containment checking
- Route buffering accounts for GPS accuracy and path width
- Projects coordinates for local distance calculations
- Bearing calculations use great circle geometry for accuracy

### Bearing Alignment Analysis
- Calculates true bearing (compass direction) for route and brunnel segments
- Finds closest segments between polylines using point-to-line projections
- Checks alignment within configurable tolerance (default 20°)
- Handles both same-direction and opposite-direction alignment
- Excludes perpendicular crossings that don't represent actual route usage

### Brunnel Merging
- Detects adjacent brunnels of the same type sharing OSM nodes
- Performs directional concatenation based on node connectivity patterns
- Merges OSM tags, coordinates, geometry, and bounding boxes
- Handles four connection patterns: forward-forward, forward-reverse, reverse-forward, reverse-reverse
- Updates route spans to reflect the full merged segment length
- Logs conflicts when tags differ between merged segments

## Limitations

- Requires internet connection for OpenStreetMap data
- Route validation excludes polar regions (±85° latitude)
- Cannot process routes crossing the antimeridian (±180° longitude)
- Dependent on OpenStreetMap data quality and completeness
- Limited to ways tagged as bridges/tunnels in OSM
- Bearing alignment works best for linear infrastructure; complex intersections may be excluded unexpectedly

## Example Output

```
06:53:46 - brunnels - INFO - Loaded GPX route with 4183 points
06:53:47 - overpass - INFO - Found 1556 brunnels near route
06:53:47 - geometry - INFO - Total route distance: 22.39 km
06:53:47 - geometry - DEBUG - Excluded 3 brunnels due to bearing misalignment
06:53:47 - overpass - INFO - Found 11/680 contained bridges and 0/876 contained tunnels
06:53:47 - merge - WARNING - Tag conflict during merge: surface='asphalt' vs 'metal_grid'; keeping first value
06:53:47 - merge - INFO - Included brunnels (post-merge):
06:53:47 - merge - INFO - Bridge: Waterfront Recreational Trail (222183028) 5.38-5.41 km (length: 0.03 km)
06:53:47 - merge - INFO - Bridge: Cherry Street (24382063;1330056252;1330056251) 7.73-7.85 km (length: 0.12 km)
06:53:47 - merge - INFO - Bridge: Waterfront Recreational Trail (1101486832;1352972087;1352972086) 8.14-8.25 km (length: 0.11 km)
06:53:47 - merge - INFO - Bridge: Waterfront Recreational Trail (1352972070) 8.61-8.67 km (length: 0.06 km)
06:53:47 - merge - INFO - Bridge: Waterfront Recreational Trail (146154648) 11.82-11.84 km (length: 0.02 km)
06:53:47 - merge - INFO - Bridge: Waterfront Recreational Trail (33398082) 19.30-19.43 km (length: 0.13 km)
06:53:47 - merge - INFO - Bridge: Waterfront Recreational Trail (33539707) 20.87-20.91 km (length: 0.05 km)

```

## Contributing

This project welcomes contributions! Please feel free to submit issues, feature requests, or pull requests.

### Development Setup

```bash
git clone https://github.com/jsmattsonjr/brunnels.git
cd brunnels
pip install -e ".[dev]"
```

### Running Tests

```bash
pytest
```

### Code Formatting

```bash
black src/brunnels/
```

## License

MIT License

## Acknowledgments

- Anthropic's Claude wrote most of the code
- Google's Jules has also made several contributions
- OpenStreetMap contributors for the bridge and tunnel data
- The Biketerra community for inspiration and feedback