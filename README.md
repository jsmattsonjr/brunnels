# Brunnels

A GPX route analysis tool that identifies bridges and tunnels along your route and visualizes them on an interactive map.

## What is a Brunnel?

"Brunnel" is a portmanteau of "bridge" and "tunnel" used in this tool to refer to both types of infrastructure collectively. This term is commonly used on the Biketerra Discord server.

## Features

- **GPX Route Processing**: Parse GPX files containing GPS tracks from cycling computers, fitness apps, or route planning tools
- **OpenStreetMap Integration**: Query real bridge and tunnel data from OpenStreetMap via the Overpass API
- **Smart Exclusion**: Exclude bridges/tunnels based on cycling relevance (bicycle access, infrastructure type)
- **Containment Analysis**: Identify which bridges/tunnels your route actually crosses vs. those merely nearby
- **Vector Alignment**: Exclude bridges/tunnels that aren't aligned with your route direction (configurable tolerance)
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
pip install -e ".[dev]"
```

### Run from Source (No Installation)

```bash
git clone https://github.com/jsmattsonjr/brunnels.git
cd brunnels
# Install dependencies only
pip install gpxpy>=1.4.2 shapely>=1.8.0 pyproj>=3.2.0 folium>=0.12.0 requests>=2.25.0
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
3. Exclude brunnels based on cycling relevance and vector alignment with your route
4. Generate an interactive map with a filename based on your input file (e.g., `route.gpx` → `route map.html`)
5. Automatically open the map in your default browser

If the output file already exists, the tool will automatically try numbered variations (e.g., `route map (1).html`, `route map (2).html`) to avoid overwriting existing files.

### Advanced Options

**If installed via pip:**
```bash
brunnels route.gpx \
  --output my_map.html \
  --query-buffer 0.5 \
  --route-buffer 5.0 \
  --bearing-tolerance 15.0 \
  --log-level DEBUG
```

**If running from source:**
```bash
python3 -m brunnels.cli route.gpx \
  --output my_map.html \
  --query-buffer 0.5 \
  --route-buffer 5.0 \
  --bearing-tolerance 15.0 \
  --log-level DEBUG
```

**For large routes (cross-country, international) that may timeout:**
```bash
brunnels large_route.gpx --timeout 300
```

### Options

- `--output FILE`: Specify output HTML filename (default: auto-generated based on input filename)
- `--query-buffer DISTANCE`: Search radius around route in meters (default: 10m)
- `--route-buffer DISTANCE`: Route containment buffer in meters (default: 3.0m)
- `--bearing-tolerance DEGREES`: Vector alignment tolerance in degrees (default: 20.0°)
- `--timeout SECONDS`: Overpass API timeout in seconds (default: 30)
- `--include-bicycle-no`: Include ways tagged `bicycle=no` in the Overpass query
- `--include-waterways`: Include ways tagged as `waterway` in the Overpass query
- `--include-active-railways`: Include ways tagged as active `railway` types (`rail`, `light_rail`, `subway`, `tram`, `narrow_gauge`, `funicular`, `monorail`, `miniature`, `preserved`)
- `--log-level LEVEL`: Set logging verbosity (DEBUG, INFO, WARNING, ERROR, CRITICAL) (default: WARNING)
- `--metrics`: Output detailed structured metrics about the processing of brunnels to stderr
- `--no-open`: Don't automatically open the HTML file in browser
- `--version`: Show program's version number and exit

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

### Brunnel List Output

The tool outputs a detailed list of all brunnels found near your route:

**Individual Brunnel Lines:**
Each line follows this format:
```
start-end km (length km) [annotation] Name/ID [exclusion reason]
```

- **Distance Information:** `1.45-1.47 km` shows the route span where the brunnel intersects your path, `(0.01 km)` shows the length of the brunnel crossing
- **Annotations:** `*` = included brunnel (full color on map), `-` = excluded brunnel (grayed out or alternate colors)
- **Names/IDs:** Named infrastructure like `Bridge: Main Street`, unnamed ways like `Bridge: <OSM 852560833>`, or compound brunnels like `Bridge: <OSM 169505851;591294837> [2 segments]`
- **Exclusion Reasons:** `(alternative)` = excluded because a closer overlapping brunnel was kept, `(misaligned)` = excluded because no segment pairs align with your route direction

**Overlap Groups:**
```
--- Overlapping -------
 3.89- 3.91 km (0.02 km) *   Bridge: <OSM 1338748628> 
 3.89- 3.91 km (0.02 km) -   Bridge: <OSM 778940105>  (alternative)
```
When multiple brunnels span the same portion of your route, they're grouped together. The closest one to your actual path is kept (`*`), while others are marked as alternatives (`-`). The dashed lines separate different overlap groups and standalone brunnels for easier reading.

### Exclusion Criteria

The tool applies smart exclusion criteria for cycling routes:

- **Excludes**: Infrastructure marked `bicycle=no`, waterways, active railways (`rail`, `light_rail`, `subway`, `tram`, `narrow_gauge`, `funicular`, `monorail`, `miniature`, `preserved`)
- **Vector alignment**: Excludes brunnels where no segment pairs are aligned with your route direction (±20° tolerance by default)

### Vector Alignment

The tool checks if bridges and tunnels are aligned with your route direction by:

1. Examining all pairs of brunnel segments and route segments within the route span
2. Calculating direction vectors for each segment pair  
3. Using dot product to measure alignment between vectors (handles both parallel and anti-parallel cases)
4. Excludes brunnels only if no segment pairs are aligned within tolerance

A brunnel is kept if any of its segments align with any route segment in the crossing area. This prevents excluding infrastructure that genuinely crosses your route, even if some segments run at different angles.

### Overlap Exclusion

When multiple parallel bridges or tunnels span similar portions of your route, the tool handles overlapping brunnels by:

- **Distance calculation**: The tool calculates the average distance from each brunnel to your route
- **Nearest selection**: The closest brunnel in each overlapping group is displayed in full color
- **Alternative display**: Other brunnels in the overlap group are displayed on the map in a different color and marked as "alternative" in the output list

### Merging

The tool automatically merges adjacent brunnels of the same type (bridge or tunnel) that share OpenStreetMap nodes. This combines fragmented infrastructure into continuous segments for cleaner visualization. The merging process:

- Detects shared nodes between adjacent segments along your route
- Updates route spans to cover the full merged length

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
- Vector alignment analysis uses dot product calculations for accuracy

### Alignment Analysis
- Calculates direction vectors for route and brunnel segments
- Examines all segment pairs between brunnel and route within the route span
- Uses dot product to measure vector alignment within configurable tolerance (default 20°)
- Handles both same-direction and opposite-direction alignment
- Excludes brunnels only when no segment pairs are aligned within tolerance

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