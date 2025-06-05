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
        individual_pattern = (
            r"Bridge: ([^(]+) \(([^)]+)\) ([\d.]+)-([\d.]+) km \(length: ([\d.]+) km\)"
        )
        for match in re.finditer(individual_pattern, self.stderr):
            self.included_brunnels.append(
                {
                    "name": match.group(1).strip(),
                    "osm_id": match.group(2),
                    "start_km": float(match.group(3)),
                    "end_km": float(match.group(4)),
                    "length_km": float(match.group(5)),
                    "type": "individual",
                }
            )

        # Parse compound bridges
        compound_pattern = r"Compound Bridge: ([^(]+) \(([^)]+)\) \[(\d+) segments\] ([\d.]+)-([\d.]+) km \(length: ([\d.]+) km\)"
        for match in re.finditer(compound_pattern, self.stderr):
            self.included_brunnels.append(
                {
                    "name": match.group(1).strip(),
                    "osm_id": match.group(2),
                    "segments": int(match.group(3)),
                    "start_km": float(match.group(4)),
                    "end_km": float(match.group(5)),
                    "length_km": float(match.group(6)),
                    "type": "compound",
                }
            )


def run_brunnels_cli(gpx_file: Path, **kwargs) -> BrunnelsTestResult:
    """Run brunnels CLI and return parsed results"""
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

        # Check if output file was created BEFORE temp dir is deleted
        output_exists = output_file.exists() if result.returncode == 0 else False

        # Copy file content if it exists (so we can validate HTML later)
        html_content = None
        if output_exists:
            try:
                with open(output_file) as f:
                    html_content = f.read()
            except Exception:
                html_content = None

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


class TestTorontoWaterfrontRoute:
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

    def test_default_settings(self, gpx_file: Path, metadata: Dict[str, Any]):
        """Test Toronto route with default settings"""
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

    def test_disable_compound_brunnels(self, gpx_file: Path, metadata: Dict[str, Any]):
        """Test with compound brunnel creation disabled"""
        scenario = next(
            s
            for s in metadata["test_scenarios"]
            if s["name"] == "disable_compound_brunnels"
        )

        result = run_brunnels_cli(gpx_file, **scenario["args"])
        assert result.exit_code == 0

        # Should have no compounds created
        assert result.metrics.get("final_included_compound", 0) == 0

        # Should have more individual brunnels than default
        default_result = run_brunnels_cli(gpx_file)
        assert (
            result.metrics["final_included_individual"]
            >= default_result.metrics["final_included_individual"]
        )

        # Validate against expected range if provided
        if "expected_included" in scenario:
            assert_in_range(
                result.metrics["final_included_total"],
                scenario["expected_included"],
                "no_compounds_total_included",
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


# Additional utility for manual testing/debugging
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


@pytest.mark.parametrize(
    "gpx_filename",
    [
        "Toronto.gpx",
        # Add more routes here as you create them:
        # "amsterdam_center.gpx",
        # "rural_trail.gpx",
        # "century_ride.gpx"
    ],
)
def test_any_route_default_settings(gpx_filename: str):
    """Generalized test that works with any GPX file that has matching JSON metadata"""
    fixtures_dir = Path(__file__).parent / "fixtures"
    gpx_file = fixtures_dir / gpx_filename
    metadata_file = gpx_file.with_suffix(".json")

    # Skip if files don't exist
    if not gpx_file.exists() or not metadata_file.exists():
        pytest.skip(f"Missing files: {gpx_file} or {metadata_file}")

    with open(metadata_file) as f:
        metadata = json.load(f)

    result = run_brunnels_cli(gpx_file)
    expected = metadata["expected_results"]

    # Basic execution
    assert result.exit_code == 0, f"CLI failed for {gpx_filename}: {result.stderr}"
    assert result.html_content is not None, f"No HTML output for {gpx_filename}"

    # Core metrics validation
    assert result.metrics["track_points"] == metadata["track_points"]
    assert abs(result.metrics["total_distance_km"] - metadata["distance_km"]) < 0.1

    # Brunnel counts validation
    assert_in_range(
        result.metrics["total_brunnels_found"],
        expected["total_brunnels_found"],
        "total_brunnels",
    )
    assert_in_range(
        result.metrics["contained_bridges"],
        expected["contained_bridges"],
        "contained_bridges",
    )
    assert_in_range(
        result.metrics["final_included_total"],
        expected["final_included_total"],
        "final_included",
    )

    # Filtering validation - check individual reasons only
    if "filtered_brunnels" in expected and result.filtering:
        filtering_expected = expected["filtered_brunnels"]

        # Check individual filtering reasons that were actually parsed
        for reason, expected_range in filtering_expected.items():
            if reason in result.filtering:
                assert_in_range(
                    result.filtering[reason], expected_range, f"filtered_{reason}"
                )


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        debug_route(sys.argv[1])
    else:
        debug_toronto_route()
