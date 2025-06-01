# Brunnels

A GPX route analysis tool that identifies bridges and tunnels along your route and visualizes them on an interactive map.

## What is a Brunnel?

"Brunnel" is a portmanteau of "bridge" and "tunnel" used in this tool to refer to both types of infrastructure collectively. This term is commonly used on the Biketerra Discord server.

## Features

- **GPX Route Processing**: Parse GPX files containing GPS tracks from cycling computers, fitness apps, or route planning tools
- **OpenStreetMap Integration**: Query real bridge and tunnel data from OpenStreetMap via the Overpass API
- **Smart Filtering**: Filter bridges/tunnels based on cycling relevance (bicycle access, infrastructure type)
- **Containment Analysis**: Identify which bridges/tunnels your route actually crosses vs. those merely nearby
- **Interactive Visualization**: Generate beautiful HTML maps with route and brunnel overlay
- **Detailed Metadata**: View comprehensive OpenStreetMap tags and properties for each brunnel
- **Adjacent Way Merging**: Automatically combines adjacent bridge/tunnel ways that share OSM nodes into single continuous brunnels

## Installation

### Requirements

- Python 3.7+
- Internet connection (for OpenStreetMap data queries)

### Install Dependencies

```bash
pip install gpxpy folium requests shapely
```

### Download

```bash
git clone https://github.com/jsmattsonjr/brunnels.git
cd brunnels
```

## Usage

### Basic Usage

```bash
python brunnels.py your_route.gpx
```

This will:
1. Parse your GPX file
2. Find all bridges and tunnels in an area extending 100m beyond your route's bounding box
3. Generate an interactive map at `brunnel_map.html`
4. Automatically open the map in your default browser

### Advanced Options

```bash
python brunnels.py route.gpx \
  --output my_map.html \
  --buffer 0.5 \
  --route-buffer 5.0 \
  --no-tag-filtering \
  --log-level DEBUG
```

### Options

- `--output FILE`: Specify output HTML filename (default: `brunnel_map.html`)
- `--buffer DISTANCE`: Search radius around route in kilometers (default: 0.1km)
- `--route-buffer DISTANCE`: Route containment buffer in meters (default: 3.0m)
- `--no-tag-filtering`: Disable filtering based on cycling relevance
- `--log-level LEVEL`: Set logging verbosity (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- `--no-open`: Don't automatically open the map in browser

### Reading from Standard Input

```bash
cat route.gpx | python brunnels.py -
```

## Understanding the Output

### Interactive Map

The generated HTML map includes:

- **Red line**: Your GPX route
- **Blue solid lines**: Bridges that your route crosses
- **Brown dashed lines**: Tunnels that your route passes through
- **Light colored lines**: Nearby bridges/tunnels that you don't cross
- **Green marker**: Route start
- **Red marker**: Route end

### Legend

- Numbers in parentheses show counts
- Click on any brunnel for detailed OpenStreetMap metadata
- Contained brunnels show route span information (start/end distances, length)

### Filtering

The tool applies smart filtering for cycling routes:

- **Keeps**: Bridges/tunnels with bicycle access allowed or `highway=cycleway`
- **Filters out**: Infrastructure marked `bicycle=no`, pure waterways, active railways
- **Grays out**: Non-contained or filtered brunnels for context

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
- Haversine distance calculations for accuracy
- Handles routes worldwide (excludes polar regions and antimeridian crossings)

### Data Sources
- Brunnel data from OpenStreetMap via Overpass API
- Respects OSM usage policies with reasonable request timeouts
- Processes OSM tags for cycling relevance and infrastructure type

### Geometric Analysis
- Uses Shapely for precise geometric containment checking
- Route buffering accounts for GPS accuracy and path width
- Projects coordinates for local distance calculations

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

## Example Output

```
06:53:46 - brunnels - INFO - Loaded GPX route with 4183 points
06:53:47 - overpass - INFO - Found 1556 brunnels near route
06:53:47 - geometry - INFO - Total route distance: 22.39 km
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

This project welcomes contributions!

## License

MIT License

## Acknowledgments

- Anthropic's Claude wrote most of the code
