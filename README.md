# Brunnels

A GPX route analysis tool that identifies bridges and tunnels along your route and visualizes them on an interactive map.

## What is a Brunnel?

"Brunnel" is a portmanteau of "bridge" and "tunnel" - a term commonly used in GIS and mapping to refer to both types of infrastructure collectively.

## Features

- **GPX Route Processing**: Parse GPX files containing GPS tracks from cycling computers, fitness apps, or route planning tools
- **OpenStreetMap Integration**: Query real bridge and tunnel data from OpenStreetMap via the Overpass API
- **Smart Filtering**: Filter bridges/tunnels based on cycling relevance (bicycle access, infrastructure type)
- **Containment Analysis**: Identify which bridges/tunnels your route actually crosses vs. those merely nearby
- **Interactive Visualization**: Generate beautiful HTML maps with route and brunnel overlay
- **Detailed Metadata**: View comprehensive OpenStreetMap tags and properties for each bridge/tunnel

## Installation

### Requirements

- Python 3.7+
- Internet connection (for OpenStreetMap data queries)

### Install Dependencies

```bash
pip install gpxpy folium requests shapely tqdm
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

- Numbers in parentheses show contained/total counts (e.g., "Bridges (3/7)" means 3 bridges crossed out of 7 nearby)
- Click on any bridge/tunnel for detailed OpenStreetMap metadata
- Contained brunnels show route span information (start/end distances, length)

### Filtering

The tool applies smart filtering for cycling routes:

- **Keeps**: Bridges/tunnels with `bicycle=yes` or `highway=cycleway`
- **Filters out**: Infrastructure marked `bicycle=no`, pure waterways, active railways
- **Grays out**: Non-contained or filtered brunnels for context

## Technical Details

### Coordinate System
- Uses WGS84 decimal degrees (standard GPS coordinates)
- Haversine distance calculations for accuracy
- Handles routes worldwide (excludes polar regions and antimeridian crossings)

### Data Sources
- Bridge/tunnel data from OpenStreetMap via Overpass API
- Respects OSM usage policies with reasonable request timeouts
- Processes OSM tags for cycling relevance and infrastructure type

### Geometric Analysis
- Uses Shapely for precise geometric containment checking
- Route buffering accounts for GPS accuracy and path width
- Projects coordinates for local distance calculations

## Limitations

- Requires internet connection for OpenStreetMap data
- Route validation excludes polar regions (±85° latitude)
- Cannot process routes crossing the antimeridian (±180° longitude)
- Dependent on OpenStreetMap data quality and completeness
- Limited to ways tagged as bridges/tunnels in OSM

## Example Output

```
14:23:15 - brunnels - INFO - Loaded GPX route with 1247 points
14:23:15 - brunnels - INFO - Querying Overpass API for bridges and tunnels...
14:23:17 - brunnels - INFO - Found 12 bridges/tunnels near route
14:23:17 - brunnels - INFO - Found 2/5 contained bridges and 1/7 contained tunnels
14:23:18 - brunnels - INFO - Map saved to brunnel_map.html
```

## Contributing

This project welcomes contributions!

## License

MIT License

## Acknowledgments

- Anthropic's Claude wrote most of the code
