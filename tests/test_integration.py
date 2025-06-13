import pytest
import json
import subprocess
import tempfile
import re
from pathlib import Path
from typing import Dict, Any, List, Optional


class BrunnelsTestResult:
    """Parse and validate brunnels CLI output"""

    def __init__(
        self,
        stdout: str,
        stderr: str,
        exit_code: int,
        html_content: Optional[str] = None,
    ):
        self.stdout = stdout
        self.stderr = stderr
        self.exit_code = exit_code
        self.html_content = html_content

        # Initialize attributes that will be set by _parse_output
        self.metrics: Dict[str, float] = {}
        self.filtering: Dict[str, int] = {}
        self.included_brunnels: List[Dict[str, Any]] = []

        self._parse_output()

    def _parse_output(self):
        """Extract metrics from structured debug output"""
        self.metrics = {}
        self.filtering = {}
        self.included_brunnels = []

        # Parse structured metrics from stderr
        in_metrics = False
        for line in self.stderr.split("\n"):
            line = line.strip()
            if "=== BRUNNELS_METRICS ===" in line:
                in_metrics = True
                continue
            elif "=== END_BRUNNELS_METRICS ===" in line:
                break
            elif in_metrics and "=" in line:
                # Extract the message part from log line format: "timestamp - module - level - message"
                # Split on " - " and take the last part (message)
                parts = line.split(" - ")
                message = parts[-1] if len(parts) >= 4 else line

                # Handle filtering reasons: "filtered_reason[outwith_route_buffer]=952"
                if message.startswith("filtered_reason["):
                    bracket_start = message.find("[")
                    bracket_end = message.find("]")
                    equals_pos = message.find("=", bracket_end)

                    if bracket_start != -1 and bracket_end != -1 and equals_pos != -1:
                        reason_key = message[bracket_start + 1 : bracket_end]
                        count_str = message[equals_pos + 1 :]
                        self.filtering[reason_key] = int(count_str)

                # Handle regular metrics: "total_brunnels_found=1515"
                elif "=" in message and not message.startswith("filtered_reason"):
                    key, value = message.split("=", 1)
                    self.metrics[key] = int(value)

        # Calculate total filtered count
        if self.filtering:
            self.filtering["total"] = sum(self.filtering.values())

        # Parse legacy metrics from non-structured output
        patterns = {
            "track_points": r"Parsed (\d+) track points from GPX file",
            "total_distance_km": r"Total route distance: ([\d.]+) km",
        }

        for key, pattern in patterns.items():
            if (
                key not in self.metrics
            ):  # Only if not already parsed from structured output
                match = re.search(pattern, self.stderr)
                if match:
                    value = match.group(1)
                    self.metrics[key] = float(value) if "." in value else int(value)

        # Parse included brunnels details
        self._parse_included_brunnels()

    def _parse_included_brunnels(self):
        """Parse individual and compound brunnel details from stderr"""
        # Parse individual bridges
        individual_bridge_pattern = (
            r"Bridge: ([^(]+) \(([^)]+)\) ([\d.]+)-([\d.]+) km \(length: ([\d.]+) km\)"
        )
        for match in re.finditer(individual_bridge_pattern, self.stderr):
            self.included_brunnels.append(
                {
                    "name": match.group(1).strip(),
                    "osm_id": match.group(2),
                    "start_km": float(match.group(3)),
                    "end_km": float(match.group(4)),
                    "length_km": float(match.group(5)),
                    "type": "individual",
                    "brunnel_type": "bridge",
                }
            )

        # Parse individual tunnels
        individual_tunnel_pattern = (
            r"Tunnel: ([^(]+) \(([^)]+)\) ([\d.]+)-([\d.]+) km \(length: ([\d.]+) km\)"
        )
        for match in re.finditer(individual_tunnel_pattern, self.stderr):
            self.included_brunnels.append(
                {
                    "name": match.group(1).strip(),
                    "osm_id": match.group(2),
                    "start_km": float(match.group(3)),
                    "end_km": float(match.group(4)),
                    "length_km": float(match.group(5)),
                    "type": "individual",
                    "brunnel_type": "tunnel",
                }
            )

        # Parse compound bridges
        compound_bridge_pattern = r"Compound Bridge: ([^(]+) \(([^)]+)\) \[(\d+) segments\] ([\d.]+)-([\d.]+) km \(length: ([\d.]+) km\)"
        for match in re.finditer(compound_bridge_pattern, self.stderr):
            self.included_brunnels.append(
                {
                    "name": match.group(1).strip(),
                    "osm_id": match.group(2),
                    "segments": int(match.group(3)),
                    "start_km": float(match.group(4)),
                    "end_km": float(match.group(5)),
                    "length_km": float(match.group(6)),
                    "type": "compound",
                    "brunnel_type": "bridge",
                }
            )

        # Parse compound tunnels
        compound_tunnel_pattern = r"Compound Tunnel: ([^(]+) \(([^)]+)\) \[(\d+) segments\] ([\d.]+)-([\d.]+) km \(length: ([\d.]+) km\)"
        for match in re.finditer(compound_tunnel_pattern, self.stderr):
            self.included_brunnels.append(
                {
                    "name": match.group(1).strip(),
                    "osm_id": match.group(2),
                    "segments": int(match.group(3)),
                    "start_km": float(match.group(4)),
                    "end_km": float(match.group(5)),
                    "length_km": float(match.group(6)),
                    "type": "compound",
                    "brunnel_type": "tunnel",
                }
            )


def run_brunnels_cli(gpx_file: Path, **kwargs) -> BrunnelsTestResult:
    """Run brunnels CLI and return parsed results"""
    import time

    with tempfile.TemporaryDirectory() as temp_dir:
        output_file = Path(temp_dir) / "test_output.html"

        cmd = [
            "python",
            "-m",
            "brunnels.cli",
            str(gpx_file),
            "--output",
            str(output_file),
            "--log-level",
            "DEBUG",
            "--no-open",
            "--metrics",  # Always include metrics for structured parsing
        ]

        # Add optional arguments
        for key, value in kwargs.items():
            arg_name = f"--{key.replace('_', '-')}"
            if isinstance(value, bool) and value:
                cmd.append(arg_name)
            elif not isinstance(value, bool):
                cmd.extend([arg_name, str(value)])

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent,  # Run from project root
        )

        # Copy file content if command succeeded
        html_content = None
        if result.returncode == 0:
            # Windows fix: Wait a moment for file to be fully written
            time.sleep(0.1)

            # Check if output file was created
            if output_file.exists():
                # Windows fix: Multiple attempts to read file
                for attempt in range(3):
                    try:
                        with open(output_file, "r", encoding="utf-8") as f:
                            html_content = f.read()
                        break  # Success, exit retry loop
                    except (IOError, OSError, PermissionError) as e:
                        if attempt < 2:  # Not the last attempt
                            time.sleep(0.1)  # Wait before retry
                            continue
                        else:
                            print(
                                f"Warning: Failed to read HTML output after 3 attempts: {e}"
                            )
                            html_content = None
            else:
                print(f"Warning: Output file {output_file} was not created")

        return BrunnelsTestResult(
            result.stdout, result.stderr, result.returncode, html_content=html_content
        )


def assert_in_range(actual: float, expected_range: str, metric_name: str):
    """Assert that actual value is within expected range"""
    if "-" in expected_range:
        min_val, max_val = map(int, expected_range.split("-"))
        assert (
            min_val <= actual <= max_val
        ), f"{metric_name}: expected {expected_range}, got {actual}"
    elif expected_range.endswith("+"):
        min_val = int(expected_range[:-1])
        assert (
            actual >= min_val
        ), f"{metric_name}: expected {expected_range}, got {actual}"
    else:
        expected = int(expected_range)
        assert actual == expected, f"{metric_name}: expected {expected}, got {actual}"


class BaseRouteTest:
    """Base class for route-specific integration tests."""

    # self.gpx_file and self.metadata are expected to be provided by subclasses
    # through pytest fixtures.

    def test_default_settings(self, gpx_file: Path, metadata: Dict[str, Any]):
        """Test route with default settings"""
        result = run_brunnels_cli(gpx_file)

        # Basic execution
        assert result.exit_code == 0, f"CLI failed: {result.stderr}"
        assert result.html_content is not None, "No HTML output generated"

        expected = metadata["expected_results"]

        # Validate core metrics
        assert result.metrics["track_points"] == metadata["track_points"]
        assert abs(result.metrics["total_distance_km"] - metadata["distance_km"]) < 0.1

        # Validate brunnel counts
        assert_in_range(
            result.metrics["total_brunnels_found"],
            expected["total_brunnels_found"],
            "total_brunnels_found",
        )
        assert_in_range(
            result.metrics["contained_bridges"],
            expected["contained_bridges"],
            "contained_bridges",
        )
        assert_in_range(
            result.metrics["contained_tunnels"],
            expected["contained_tunnels"],
            "contained_tunnels",
        )
        assert_in_range(
            result.metrics["final_included_total"],
            expected["final_included_total"],
            "final_included_total",
        )
        assert_in_range(
            result.metrics["final_included_individual"],
            expected["final_included_individual"],
            "final_included_individual",
        )
        assert_in_range(
            result.metrics["final_included_compound"],
            expected["final_included_compound"],
            "final_included_compound",
        )

        # Validate filtering - check individual reasons only
        filtering_expected = expected["filtered_brunnels"]

        # Check individual filtering reasons that were actually parsed
        for reason, expected_range in filtering_expected.items():
            if reason in result.filtering:
                assert_in_range(
                    result.filtering[reason], expected_range, f"filtered_{reason}"
                )

    def test_html_output_validity(self, gpx_file: Path):
        """Test that generated HTML is valid and contains expected elements"""
        result = run_brunnels_cli(gpx_file)
        assert result.exit_code == 0
        assert result.html_content is not None, "No HTML content generated"

        html_content = result.html_content

        # Basic HTML structure
        assert "<html" in html_content
        assert "</html>" in html_content
        assert "folium" in html_content.lower()

        # Map elements
        assert "leaflet" in html_content.lower()
        assert "polyline" in html_content.lower()

        # Legend elements
        assert "legend" in html_content.lower()
        assert "bridge" in html_content.lower()

        # Route markers
        assert "marker" in html_content.lower()


class TestTorontoWaterfrontRoute(BaseRouteTest):
    """Integration tests for Toronto Waterfront Recreation Trail"""

    @pytest.fixture
    def metadata(self, gpx_file: Path) -> Dict[str, Any]:
        """Load metadata JSON file matching the GPX basename"""
        metadata_file = gpx_file.with_suffix(".json")
        with open(metadata_file) as f:
            return json.load(f)

    @pytest.fixture
    def gpx_file(self) -> Path:
        """Path to Toronto GPX file"""
        return Path(__file__).parent / "fixtures" / "Toronto.gpx"

    def test_known_bridges_present(self, gpx_file: Path, metadata: Dict[str, Any]):
        """Test that known bridges are detected correctly"""
        result = run_brunnels_cli(gpx_file)
        assert result.exit_code == 0

        known_bridges = metadata["known_bridges"]

        # Collect all OSM IDs from both individual and compound brunnels
        included_osm_ids = set()
        for brunnel in result.included_brunnels:
            if brunnel["type"] == "compound":
                # For compound brunnels, split the semicolon-separated IDs
                ids = brunnel["osm_id"].split(";")
                included_osm_ids.update(ids)
            else:
                included_osm_ids.add(brunnel["osm_id"])

        # Check that major known bridges are found
        for bridge in known_bridges:
            if "osm_way_id" in bridge:
                assert (
                    str(bridge["osm_way_id"]) in included_osm_ids
                ), f"Known bridge {bridge['name']} (OSM {bridge['osm_way_id']}) not found"
            elif "osm_way_ids" in bridge and bridge["type"] == "compound_bridge":
                # For compound bridges, check if any component is found
                bridge_ids = {str(oid) for oid in bridge["osm_way_ids"]}
                found_ids = bridge_ids & included_osm_ids
                assert (
                    len(found_ids) > 0
                ), f"Compound bridge {bridge['name']} components not found. Expected: {bridge_ids}, Found: {included_osm_ids}"

    def test_strict_bearing_tolerance(self, gpx_file: Path, metadata: Dict[str, Any]):
        """Test with stricter bearing tolerance"""
        scenario = next(
            s
            for s in metadata["test_scenarios"]
            if s["name"] == "strict_bearing_tolerance"
        )

        result = run_brunnels_cli(gpx_file, **scenario["args"])
        assert result.exit_code == 0

        # Should have same or fewer included brunnels
        default_result = run_brunnels_cli(gpx_file)
        assert (
            result.metrics["final_included_total"]
            <= default_result.metrics["final_included_total"]
        )

        # Validate against expected range
        assert_in_range(
            result.metrics["final_included_total"],
            scenario["expected_final_included_total"],
            "strict_bearing_included",
        )

    def test_performance_benchmarks(self, gpx_file: Path, metadata: Dict[str, Any]):
        """Test performance meets expected benchmarks"""
        import time
        import psutil
        import os

        process = psutil.Process(os.getpid())
        start_memory = process.memory_info().rss / 1024 / 1024  # MB
        start_time = time.time()

        result = run_brunnels_cli(gpx_file)

        end_time = time.time()
        end_memory = process.memory_info().rss / 1024 / 1024  # MB

        processing_time = end_time - start_time
        memory_used = end_memory - start_memory

        benchmarks = metadata["performance_benchmarks"]

        # Parse expected time range
        time_range = benchmarks["processing_time_seconds"]
        min_time, max_time = map(int, time_range.split("-"))

        assert result.exit_code == 0
        assert (
            processing_time <= max_time
        ), f"Processing took {processing_time:.1f}s, expected <{max_time}s"

        # Memory should be reasonable (this is a rough check)
        max_memory = int(benchmarks["memory_usage_mb"].replace("<", ""))
        assert (
            memory_used < max_memory
        ), f"Memory usage {memory_used:.1f}MB exceeded {max_memory}MB"


class TestTransfagarasanRoute(BaseRouteTest):
    """Integration tests for Transfăgărășan Mountain Pass"""

    @pytest.fixture
    def metadata(self, gpx_file: Path) -> Dict[str, Any]:
        """Load metadata JSON file matching the GPX basename"""
        metadata_file = gpx_file.with_suffix(".json")
        with open(metadata_file) as f:
            return json.load(f)

    @pytest.fixture
    def gpx_file(self) -> Path:
        """Path to Transfăgărășan GPX file"""
        return Path(__file__).parent / "fixtures" / "Transfagarasan.gpx"

    def test_known_bridges_and_tunnels_present(
        self, gpx_file: Path, metadata: Dict[str, Any]
    ):
        """Test that known bridges and tunnels are detected correctly"""
        result = run_brunnels_cli(gpx_file)
        assert result.exit_code == 0

        # Collect all OSM IDs from included brunnels
        included_osm_ids = set()
        for brunnel in result.included_brunnels:
            if brunnel["type"] == "compound":
                ids = brunnel["osm_id"].split(";")
                included_osm_ids.update(ids)
            else:
                included_osm_ids.add(brunnel["osm_id"])

        # Check known bridges
        for bridge in metadata["known_bridges"]:
            assert (
                str(bridge["osm_way_id"]) in included_osm_ids
            ), f"Known bridge {bridge['name']} (OSM {bridge['osm_way_id']}) not found"

        # Check known tunnels
        for tunnel in metadata["known_tunnels"]:
            assert (
                str(tunnel["osm_way_id"]) in included_osm_ids
            ), f"Known tunnel {tunnel['name']} (OSM {tunnel['osm_way_id']}) not found"

    def test_tunnel_concentration_area(self, gpx_file: Path, metadata: Dict[str, Any]):
        """Test that tunnel concentration around 16-22km mark is detected"""
        result = run_brunnels_cli(gpx_file)
        assert result.exit_code == 0

        # Count tunnels in the 16-22km range
        tunnels_in_range = [
            b
            for b in result.included_brunnels
            if 16.0 <= b.get("start_km", 0) <= 22.0
            and b.get("brunnel_type") == "tunnel"
        ]

        # Should have significant tunnel concentration in this area
        assert (
            len(tunnels_in_range) >= 5
        ), f"Expected >=5 tunnels in 16-22km range, found {len(tunnels_in_range)}"

    def test_no_compound_brunnels_expected(
        self, gpx_file: Path, metadata: Dict[str, Any]
    ):
        """Test that no compound brunnels are created (infrastructure is well-spaced)"""
        result = run_brunnels_cli(gpx_file)
        assert result.exit_code == 0

        compound_count = len(
            [b for b in result.included_brunnels if b["type"] == "compound"]
        )
        assert (
            compound_count == 0
        ), f"Expected 0 compound brunnels, found {compound_count}"

    def test_mountain_road_bearing_alignment(
        self, gpx_file: Path, metadata: Dict[str, Any]
    ):
        """Test bearing alignment on serpentine mountain road"""
        # Test with stricter tolerance
        strict_result = run_brunnels_cli(gpx_file, bearing_tolerance=10.0)
        assert strict_result.exit_code == 0

        # Test with default tolerance
        default_result = run_brunnels_cli(gpx_file)
        assert default_result.exit_code == 0

        # Stricter tolerance should result in same or fewer included brunnels
        assert (
            strict_result.metrics["final_included_total"]
            <= default_result.metrics["final_included_total"]
        ), "Stricter bearing tolerance should not increase included brunnels"
        # Additional utility for manual testing/debugging


class TestArea51Route(BaseRouteTest):
    """Integration tests for Area 51 Desert Route (zero brunnels edge case)"""

    @pytest.fixture
    def metadata(self, gpx_file: Path) -> Dict[str, Any]:
        """Load metadata JSON file matching the GPX basename"""
        metadata_file = gpx_file.with_suffix(".json")
        with open(metadata_file) as f:
            return json.load(f)

    @pytest.fixture
    def gpx_file(self) -> Path:
        """Path to Area51 GPX file"""
        return Path(__file__).parent / "fixtures" / "Area51.gpx"

    def test_zero_brunnels_html_output(self, gpx_file: Path):
        """Test that HTML output is valid when no brunnels are found"""
        result = run_brunnels_cli(gpx_file)
        assert result.exit_code == 0
        assert result.html_content is not None

        html_content = result.html_content

        # Basic HTML structure should still be present
        assert "<html" in html_content
        assert "</html>" in html_content
        assert "folium" in html_content.lower()

        # Map elements should still exist
        assert "leaflet" in html_content.lower()

        # Legend should show (0) counts
        assert "bridge" in html_content.lower()
        assert "(0)" in html_content  # Should show 0 counts in legend

        # Route should still be displayed
        assert "polyline" in html_content.lower()
        assert "marker" in html_content.lower()

    def test_small_query_area_performance(
        self, gpx_file: Path, metadata: Dict[str, Any]
    ):
        """Test performance with very small query area"""
        import time

        start_time = time.time()
        result = run_brunnels_cli(gpx_file)
        end_time = time.time()

        processing_time = end_time - start_time
        benchmarks = metadata["performance_benchmarks"]

        assert result.exit_code == 0

        # Should be very fast with small query area
        max_time = int(benchmarks["processing_time_seconds"].split("-")[1])
        assert (
            processing_time <= max_time
        ), f"Processing took {processing_time:.1f}s, expected <{max_time}s"

    def test_no_brunnels_message_logging(self, gpx_file: Path):
        """Test that appropriate message is logged when no brunnels are found"""
        result = run_brunnels_cli(gpx_file)
        assert result.exit_code == 0

        # Should contain the "No brunnels included" message
        assert "No brunnels included in final map" in result.stderr

    def test_edge_case_various_settings(self, gpx_file: Path):
        """Test zero brunnels scenario with various parameter combinations"""
        # Test with different route buffer sizes
        result_small_buffer = run_brunnels_cli(gpx_file, route_buffer=1.0)
        result_large_buffer = run_brunnels_cli(gpx_file, route_buffer=50.0)

        assert result_small_buffer.exit_code == 0
        assert result_large_buffer.exit_code == 0

        # Both should still find 0 brunnels
        assert result_small_buffer.metrics["final_included_total"] == 0
        assert result_large_buffer.metrics["final_included_total"] == 0

        # Test with default tag filtering (always on)
        result_default_filter = run_brunnels_cli(gpx_file)
        assert result_default_filter.exit_code == 0
        assert result_default_filter.metrics["final_included_total"] == 0

        # Test with strict bearing tolerance
        result_strict = run_brunnels_cli(gpx_file, bearing_tolerance=5.0)
        assert result_strict.exit_code == 0
        assert result_strict.metrics["final_included_total"] == 0


class TestPaulRevereRoute(BaseRouteTest):
    """Integration tests for Paul Revere Trail (overlap filtering and urban density)"""

    @pytest.fixture
    def metadata(self, gpx_file: Path) -> Dict[str, Any]:
        """Load metadata JSON file matching the GPX basename"""
        metadata_file = gpx_file.with_suffix(".json")
        with open(metadata_file) as f:
            return json.load(f)

    @pytest.fixture
    def gpx_file(self) -> Path:
        """Path to PaulRevere GPX file"""
        return Path(__file__).parent / "fixtures" / "PaulRevere.gpx"

    def test_overlap_filtering_with_increased_buffer(
        self, gpx_file: Path, metadata: Dict[str, Any]
    ):
        """Test overlap filtering with increased route buffer (key feature of this route)"""
        # Test with route_buffer=5.0 (required to detect overlapping brunnels)
        result = run_brunnels_cli(gpx_file, route_buffer=5.0)
        assert result.exit_code == 0

        # Should have overlap filtering active
        assert "not_nearest_among_overlapping_brunnels" in result.filtering
        overlap_filtered = result.filtering["not_nearest_among_overlapping_brunnels"]
        assert (
            overlap_filtered >= 1
        ), f"Expected >=1 overlap filtered, got {overlap_filtered}"

        # Test without overlap filtering disabled
        no_overlap_result = run_brunnels_cli(
            gpx_file, route_buffer=5.0, no_overlap_filtering=True
        )
        assert no_overlap_result.exit_code == 0

        # Should have same or more included brunnels when overlap filtering is disabled
        assert (
            no_overlap_result.metrics["final_included_total"]
            >= result.metrics["final_included_total"]
        ), "Disabling overlap filtering should not reduce included brunnels"

    def test_known_bridges_present(self, gpx_file: Path, metadata: Dict[str, Any]):
        """Test that known bridges are detected correctly"""
        result = run_brunnels_cli(gpx_file, route_buffer=5.0)  # Use increased buffer
        assert result.exit_code == 0

        known_bridges = metadata["known_bridges"]

        # Collect all OSM IDs from both individual and compound brunnels
        included_osm_ids = set()
        for brunnel in result.included_brunnels:
            if brunnel["type"] == "compound":
                # For compound brunnels, split the semicolon-separated IDs
                ids = brunnel["osm_id"].split(";")
                included_osm_ids.update(ids)
            else:
                included_osm_ids.add(brunnel["osm_id"])

        # Check that major known bridges are found
        for bridge in known_bridges:
            if "osm_way_id" in bridge:
                assert (
                    str(bridge["osm_way_id"]) in included_osm_ids
                ), f"Known bridge {bridge['name']} (OSM {bridge['osm_way_id']}) not found"
            elif "osm_way_ids" in bridge and bridge["type"] == "compound_bridge":
                # For compound bridges, check if components are found
                bridge_ids = {str(oid) for oid in bridge["osm_way_ids"]}
                found_ids = bridge_ids & included_osm_ids
                assert (
                    len(found_ids) > 0
                ), f"Compound bridge {bridge['name']} components not found. Expected: {bridge_ids}, Found: {included_osm_ids}"

    def test_compound_brunnel_creation(self, gpx_file: Path, metadata: Dict[str, Any]):
        """Test that compound brunnels are created correctly"""
        result = run_brunnels_cli(gpx_file, route_buffer=5.0)
        assert result.exit_code == 0

        # Should have at least one compound brunnel
        compound_brunnels = [
            b for b in result.included_brunnels if b["type"] == "compound"
        ]
        assert (
            len(compound_brunnels) >= 1
        ), f"Expected >=1 compound brunnel, found {len(compound_brunnels)}"

        # Check the High Street compound bridge specifically
        high_street_compound = next(
            (b for b in compound_brunnels if "High Street" in b["name"]), None
        )
        assert high_street_compound is not None, "High Street compound bridge not found"
        assert (
            high_street_compound["segments"] == 2
        ), "High Street compound should have 2 segments"

    def test_minuteman_bikeway_bridges(self, gpx_file: Path, metadata: Dict[str, Any]):
        """Test that multiple Minuteman Bikeway bridges are detected"""
        result = run_brunnels_cli(gpx_file, route_buffer=5.0)
        assert result.exit_code == 0

        # Count Minuteman Bikeway bridges
        minuteman_bridges = [
            b
            for b in result.included_brunnels
            if "Minuteman Bikeway" in b.get("name", "")
        ]

        # Should find multiple Minuteman Bikeway crossings
        assert (
            len(minuteman_bridges) >= 4
        ), f"Expected >=4 Minuteman Bikeway bridges, found {len(minuteman_bridges)}"

        # Verify they're spread along the route (should be in 15-23km range)
        for bridge in minuteman_bridges:
            assert (
                15.0 <= bridge["start_km"] <= 23.0
            ), f"Minuteman bridge at {bridge['start_km']}km outside expected range"

    def test_urban_density_performance(self, gpx_file: Path, metadata: Dict[str, Any]):
        """Test performance with high-density urban brunnel data"""
        import time
        import psutil
        import os

        process = psutil.Process(os.getpid())
        start_memory = process.memory_info().rss / 1024 / 1024  # MB
        start_time = time.time()

        result = run_brunnels_cli(gpx_file, route_buffer=5.0)

        end_time = time.time()
        end_memory = process.memory_info().rss / 1024 / 1024  # MB

        processing_time = end_time - start_time
        memory_used = end_memory - start_memory

        benchmarks = metadata["performance_benchmarks"]

        assert result.exit_code == 0

        # Parse expected time range
        time_range = benchmarks["processing_time_seconds"]
        min_time, max_time = map(int, time_range.split("-"))

        assert (
            processing_time <= max_time
        ), f"Processing took {processing_time:.1f}s, expected <{max_time}s"

        # Memory should be reasonable for high-density route
        max_memory = int(benchmarks["memory_usage_mb"].replace("<", ""))
        assert (
            memory_used < max_memory
        ), f"Memory usage {memory_used:.1f}MB exceeded {max_memory}MB"

    def test_historical_trail_characteristics(
        self, gpx_file: Path, metadata: Dict[str, Any]
    ):
        """Test characteristics specific to historic trail routing"""
        result = run_brunnels_cli(gpx_file, route_buffer=5.0)
        assert result.exit_code == 0

        # Should have good mix of named and unnamed bridges
        named_bridges = [
            b for b in result.included_brunnels if b.get("name", "unnamed") != "unnamed"
        ]
        unnamed_bridges = [
            b for b in result.included_brunnels if b.get("name", "unnamed") == "unnamed"
        ]

        assert (
            len(named_bridges) >= 6
        ), f"Expected >=6 named bridges, found {len(named_bridges)}"
        assert (
            len(unnamed_bridges) >= 4
        ), f"Expected >=4 unnamed bridges, found {len(unnamed_bridges)}"

        # Should cross major infrastructure (Massachusetts Avenue, Main Street)
        major_streets = ["Massachusetts Avenue", "Main Street"]
        found_major_streets = [
            street
            for street in major_streets
            if any(street in b.get("name", "") for b in result.included_brunnels)
        ]

        assert (
            len(found_major_streets) >= 2
        ), f"Expected major street crossings, found: {found_major_streets}"

    def test_bearing_alignment_filtering(
        self, gpx_file: Path, metadata: Dict[str, Any]
    ):
        """Test bearing alignment filtering effectiveness"""
        # Test with default tolerance
        default_result = run_brunnels_cli(gpx_file, route_buffer=5.0)
        assert default_result.exit_code == 0

        # Test with strict tolerance
        strict_result = run_brunnels_cli(
            gpx_file, route_buffer=5.0, bearing_tolerance=10.0
        )
        assert strict_result.exit_code == 0

        # Stricter tolerance should result in same or fewer included brunnels
        assert (
            strict_result.metrics["final_included_total"]
            <= default_result.metrics["final_included_total"]
        ), "Stricter bearing tolerance should not increase included brunnels"

        # Check that some brunnels were filtered for bearing misalignment
        if "not_aligned_with_route" in default_result.filtering:
            assert (
                default_result.filtering["not_aligned_with_route"] >= 3
            ), "Expected some bearing misalignment filtering"


def debug_route(gpx_filename: str):
    """Run any route and print detailed comparison with expected values"""
    gpx_file = Path(f"tests/fixtures/{gpx_filename}")
    metadata_file = gpx_file.with_suffix(".json")

    if not gpx_file.exists():
        print(f"GPX file not found: {gpx_file}")
        return
    if not metadata_file.exists():
        print(f"Metadata file not found: {metadata_file}")
        return

    with open(metadata_file) as f:
        metadata = json.load(f)

    result = run_brunnels_cli(gpx_file)
    expected = metadata["expected_results"]

    print(f"=== {metadata['route_name']} Test Results ===")
    print(f"Exit code: {result.exit_code}")
    print(f"HTML generated: {'Yes' if result.html_content else 'No'}")
    print(
        f"Track points: {result.metrics.get('track_points', 'N/A')} (expected: {metadata['track_points']})"
    )
    print(
        f"Total brunnels: {result.metrics.get('total_brunnels_found', 'N/A')} (expected: {expected['total_brunnels_found']})"
    )
    print(
        f"Contained bridges: {result.metrics.get('contained_bridges', 'N/A')} (expected: {expected['contained_bridges']})"
    )
    print(
        f"Final included total: {result.metrics.get('final_included_total', 'N/A')} (expected: {expected['final_included_total']})"
    )
    print(
        f"Final included individual: {result.metrics.get('final_included_individual', 'N/A')} (expected: {expected['final_included_individual']})"
    )
    print(
        f"Final included compound: {result.metrics.get('final_included_compound', 'N/A')} (expected: {expected['final_included_compound']})"
    )

    print("\n=== Filtering Results ===")
    filtering_expected = expected["filtered_brunnels"]
    print(
        f"Total filtered: {result.filtering.get('total', 'N/A')} (expected: {filtering_expected['total']})"
    )

    print("\n=== Individual Filter Reasons ===")
    for reason, expected_range in filtering_expected.items():
        if reason != "total":
            actual = result.filtering.get(reason, "N/A")
            print(f"  {reason}: {actual} (expected: {expected_range})")

    print("\n=== Included Brunnels ===")
    individual_count = len(
        [b for b in result.included_brunnels if b["type"] == "individual"]
    )
    compound_count = len(
        [b for b in result.included_brunnels if b["type"] == "compound"]
    )
    print(
        f"Found {individual_count} individual + {compound_count} compound = {len(result.included_brunnels)} total brunnels"
    )

    for brunnel in result.included_brunnels:
        if brunnel["type"] == "compound":
            print(
                f"  Compound: {brunnel['name']} ({brunnel['osm_id']}) [{brunnel['segments']} segments] at {brunnel['start_km']:.2f}km"
            )
        else:
            print(
                f"  Individual: {brunnel['name']} ({brunnel['osm_id']}) at {brunnel['start_km']:.2f}km"
            )

    if result.exit_code != 0:
        print(f"\n=== Error Output ===")
        print(result.stderr)


def debug_toronto_route():
    """Run Toronto route and print detailed comparison with expected values"""
    debug_route("Toronto.gpx")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        debug_route(sys.argv[1])
    else:
        debug_toronto_route()
