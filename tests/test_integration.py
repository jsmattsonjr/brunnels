import os
import pytest
import json
import subprocess
import tempfile
import re
import time
from pathlib import Path
from typing import Dict, Any, List, Optional


# Global cache for CLI results to avoid re-running expensive operations
_CLI_RESULT_CACHE: Dict[tuple, "BrunnelsTestResult"] = {}


def run_brunnels_cli(gpx_file: Path, **kwargs) -> "BrunnelsTestResult":
    """Run brunnels CLI with caching based on gpx_file and kwargs"""
    # Create cache key from gpx_file and sorted kwargs
    cache_key = (str(gpx_file), tuple(sorted(kwargs.items())))

    if cache_key in _CLI_RESULT_CACHE:
        return _CLI_RESULT_CACHE[cache_key]

    # Run CLI and cache result
    start_time = time.time()
    result = _run_brunnels_cli(gpx_file, **kwargs)
    end_time = time.time()

    # Store processing time for performance tests
    result.processing_time = end_time - start_time

    _CLI_RESULT_CACHE[cache_key] = result
    return result


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
        self.exclusion_details: Dict[str, int] = {}
        self.included_brunnels: List[Dict[str, Any]] = []
        self.processing_time: float = 0.0

        self._parse_output()

    def _parse_output(self):
        """Extract metrics from structured debug output"""
        self.metrics = {}
        self.exclusion_details = {}
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
                # Direct stderr output format (no logging prefixes)
                message = line

                # Handle exclusion reasons: "excluded_reason[outlier][bridge]=530"
                if message.startswith("excluded_reason["):
                    # Find the first bracket pair for the reason
                    first_bracket_start = message.find("[")
                    first_bracket_end = message.find("]")

                    # Check if there's a second bracket pair for the type
                    second_bracket_start = message.find("[", first_bracket_end + 1)
                    second_bracket_end = message.find("]", second_bracket_start + 1)
                    equals_pos = message.find("=")

                    if (
                        first_bracket_start != -1
                        and first_bracket_end != -1
                        and second_bracket_start != -1
                        and second_bracket_end != -1
                        and equals_pos != -1
                    ):
                        # New format: excluded_reason[reason][type]=count
                        reason_key = message[
                            first_bracket_start + 1 : first_bracket_end
                        ]
                        count_str = message[equals_pos + 1 :]
                        count = int(count_str)

                        # Aggregate counts by reason across bridge and tunnel types
                        if reason_key not in self.exclusion_details:
                            self.exclusion_details[reason_key] = 0
                        self.exclusion_details[reason_key] += count
                    elif (
                        first_bracket_start != -1
                        and first_bracket_end != -1
                        and equals_pos != -1
                    ):
                        # Old format: excluded_reason[reason]=count
                        reason_key = message[
                            first_bracket_start + 1 : first_bracket_end
                        ]
                        count_str = message[equals_pos + 1 :]
                        self.exclusion_details[reason_key] = int(count_str)

                # Handle regular metrics: "total_brunnels_found=1515"
                elif "=" in message and not message.startswith("excluded_reason"):
                    key, value = message.split("=", 1)
                    self.metrics[key] = int(value)

        # Calculate total excluded count
        if self.exclusion_details:
            self.exclusion_details["total"] = sum(self.exclusion_details.values())

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
        """Parse individual and compound brunnel details from stdout"""
        # New format: " 5.39- 5.42 km (0.03 km) * Bridge: Waterfront Recreational Trail "
        # or: " 7.74- 7.79 km (0.04 km) * Bridge: Cherry Street [3 segments] "

        # Parse all brunnels (bridges and tunnels, individual and compound)
        # Pattern matches: distance range, length, annotation (*/-), type, name, optional segments
        brunnel_pattern = r"\s*([\d.]+)-\s*([\d.]+) km \(([\d.]+) km\) ([*-])\s+(Bridge|Tunnel): ([^\[\(]+?)(?:\s*\[(\d+) segments\])?\s*(?:\([^)]+\))?\s*$"

        for match in re.finditer(brunnel_pattern, self.stdout, re.MULTILINE):
            start_km = float(match.group(1))
            end_km = float(match.group(2))
            length_km = float(match.group(3))
            annotation = match.group(4)
            brunnel_type_str = match.group(5).lower()
            name = match.group(6).strip()
            segments = match.group(7)

            # Only include brunnels marked with '*' (included)
            if annotation != "*":
                continue

            # Determine if compound based on segments
            is_compound = segments is not None

            # Extract OSM ID from name if it's in <OSM xxx> format or <OSM xxx;yyy;zzz> format
            osm_id = "unknown"
            if name.startswith("<OSM ") and name.endswith(">"):
                osm_id = name[5:-1]  # Remove "<OSM " and ">"

            brunnel_data = {
                "name": name,
                "osm_id": osm_id,
                "start_km": start_km,
                "end_km": end_km,
                "length_km": length_km,
                "type": "compound" if is_compound else "individual",
                "brunnel_type": brunnel_type_str,
            }

            if is_compound:
                brunnel_data["segments"] = int(segments)

            self.included_brunnels.append(brunnel_data)

    def get_included_identifiers(self):
        """Extract OSM IDs and names from included brunnels.

        Returns:
            Tuple[Set[str], Set[str]]: (osm_ids, names) - OSM IDs and names of included brunnels
        """
        included_osm_ids = set()
        included_names = set()

        for brunnel in self.included_brunnels:
            if brunnel["type"] == "compound":
                if brunnel["osm_id"] != "unknown":
                    ids = brunnel["osm_id"].split(";")
                    included_osm_ids.update(ids)
            else:
                if brunnel["osm_id"] != "unknown":
                    included_osm_ids.add(brunnel["osm_id"])
            # Always collect the name for name-based matching
            included_names.add(brunnel["name"])

        return included_osm_ids, included_names

    def assert_bridges_found(self, expected_bridges, context=""):
        """Assert that expected bridges are found by name or OSM ID.

        Args:
            expected_bridges: List of bridge metadata dictionaries
            context: Additional context for error messages (e.g., "with bicycle infrastructure")
        """
        included_osm_ids, included_names = self.get_included_identifiers()

        for bridge in expected_bridges:
            if "osm_way_id" in bridge:
                # Simple bridge - check by name or OSM ID
                bridge_found = (
                    str(bridge["osm_way_id"]) in included_osm_ids
                    or bridge["name"] in included_names
                )
                error_msg = f"Known bridge {bridge['name']} (OSM {bridge['osm_way_id']}) not found"
                if context:
                    error_msg += f" {context}"
                assert bridge_found, error_msg

            elif "osm_way_ids" in bridge and bridge["type"] == "compound_bridge":
                # Compound bridge - check if components are found (by name or OSM ID)
                bridge_ids = {str(oid) for oid in bridge["osm_way_ids"]}
                found_ids = bridge_ids & included_osm_ids
                # For compound bridges, check if the bridge name appears in any of the included names
                name_found = any(bridge["name"] in name for name in included_names)
                bridge_found = len(found_ids) > 0 or name_found

                error_msg = f"Compound bridge {bridge['name']} components not found"
                if context:
                    error_msg += f" {context}"
                error_msg += f". Expected: {bridge_ids}, Found: {included_osm_ids}"
                assert bridge_found, error_msg

    def assert_tunnels_found(self, expected_tunnels, context=""):
        """Assert that expected tunnels are found by name or OSM ID.

        Args:
            expected_tunnels: List of tunnel metadata dictionaries
            context: Additional context for error messages
        """
        included_osm_ids, included_names = self.get_included_identifiers()

        for tunnel in expected_tunnels:
            tunnel_found = (
                str(tunnel["osm_way_id"]) in included_osm_ids
                or tunnel["name"] in included_names
            )
            error_msg = (
                f"Known tunnel {tunnel['name']} (OSM {tunnel['osm_way_id']}) not found"
            )
            if context:
                error_msg += f" {context}"
            assert tunnel_found, error_msg


def _run_brunnels_cli(gpx_file: Path, **kwargs) -> BrunnelsTestResult:
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

        # Log failure details for debugging intermittent issues
        if result.returncode != 0:
            print(f"CLI failed for {gpx_file}")
            print(f"Command: {' '.join(cmd)}")
            print(f"Exit code: {result.returncode}")
            print(f"STDERR: {result.stderr}")
            print(f"STDOUT: {result.stdout}")

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

    @pytest.fixture
    def default_result(self, gpx_file: Path) -> BrunnelsTestResult:
        """Run CLI with default settings using cache"""
        return run_brunnels_cli(gpx_file)

    def assert_known_bridges_present(
        self, result: BrunnelsTestResult, metadata: Dict[str, Any], context=""
    ):
        """Assert that known bridges from metadata are found in results.

        Args:
            result: BrunnelsTestResult containing parsed CLI output
            metadata: Route metadata containing known_bridges
            context: Additional context for error messages
        """
        known_bridges = metadata.get("known_bridges", [])
        if known_bridges:
            result.assert_bridges_found(known_bridges, context)

    def assert_known_tunnels_present(
        self, result: BrunnelsTestResult, metadata: Dict[str, Any], context=""
    ):
        """Assert that known tunnels from metadata are found in results.

        Args:
            result: BrunnelsTestResult containing parsed CLI output
            metadata: Route metadata containing known_tunnels
            context: Additional context for error messages
        """
        known_tunnels = metadata.get("known_tunnels", [])
        if known_tunnels:
            result.assert_tunnels_found(known_tunnels, context)

    def assert_known_infrastructure_present(
        self, result: BrunnelsTestResult, metadata: Dict[str, Any], context=""
    ):
        """Assert that both known bridges and tunnels from metadata are found in results.

        Args:
            result: BrunnelsTestResult containing parsed CLI output
            metadata: Route metadata containing known_bridges and known_tunnels
            context: Additional context for error messages
        """
        self.assert_known_bridges_present(result, metadata, context)
        self.assert_known_tunnels_present(result, metadata, context)

    def test_default_settings(
        self, default_result: BrunnelsTestResult, metadata: Dict[str, Any]
    ):
        """Test route with default settings"""
        result = default_result

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

        # Validate exclusion details - check individual reasons only
        # Assuming 'expected["filtered_brunnels"]' key from JSON is stable for this subtask
        exclusion_expected_json_data = expected["filtered_brunnels"]

        # Check individual exclusion reasons that were actually parsed
        for reason, expected_range in exclusion_expected_json_data.items():
            if reason in result.exclusion_details:
                assert_in_range(
                    result.exclusion_details[reason],
                    expected_range,
                    f"excluded_{reason}",
                )

    def test_html_output_validity(self, default_result: BrunnelsTestResult):
        """Test that generated HTML is valid and contains expected elements"""
        result = default_result
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

        self.assert_known_bridges_present(result, metadata)

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

    @pytest.mark.skipif(os.getenv("CI") == "true", reason="Skip in CI environment")
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

        self.assert_known_infrastructure_present(result, metadata)

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

    def test_include_waterways_option(self, gpx_file: Path, metadata: Dict[str, Any]):
        """Test --include-waterways option includes waterway infrastructure"""
        result = run_brunnels_cli(
            gpx_file, include_waterways=True, bearing_tolerance=90, route_buffer=10.0
        )
        assert result.exit_code == 0

        # Validate the exact metrics observed with --include-waterways, --bearing-tolerance=90, --route-buffer=10
        expected_metrics = {
            "total_brunnels_found": 55,
            "total_bridges_found": 35,
            "total_tunnels_found": 20,
            "contained_bridges": 20,  # Updated: one more bridge included
            "contained_tunnels": 13,  # Updated: more tunnels included with larger buffer
            "final_included_individual": 33,  # Updated: total included individual brunnels
            "final_included_compound": 0,
            "final_included_total": 33,  # Updated: total included brunnels
        }

        for metric, expected_value in expected_metrics.items():
            actual_value = result.metrics.get(metric)
            assert (
                actual_value == expected_value
            ), f"{metric}: expected {expected_value}, got {actual_value}"

        # Validate exclusion metrics (updated for --bearing-tolerance=90, --route-buffer=10)
        expected_exclusion_details = {
            "outlier": 22,  # Updated: 15 bridges + 7 tunnels excluded
            "misaligned": 0,  # Updated: 90° tolerance includes all aligned brunnels
        }

        for exclusion_reason, expected_count in expected_exclusion_details.items():
            actual_count = result.exclusion_details.get(
                exclusion_reason, 0
            )  # Default to 0 if key doesn't exist
            assert (
                actual_count == expected_count
            ), f"excluded_{exclusion_reason}: expected {expected_count}, got {actual_count}"

        # Validate that HTML contains waterway entries
        assert result.html_content is not None, "No HTML content generated"

        # Count waterway entries in HTML (should be 2 'tunnel:culvert' with waterway tags)
        waterway_entries = result.html_content.count("waterway")
        assert (
            waterway_entries == 2
        ), f"Expected 2 waterway entries in HTML, found {waterway_entries}"

        # Verify waterway tags are highlighted in red (indicating filtered infrastructure)
        waterway_highlighted_entries = result.html_content.count(
            "<span style='color: red;'><i>waterway:</i>"
        )
        assert (
            waterway_highlighted_entries == 2
        ), f"Expected 2 highlighted waterway tags, found {waterway_highlighted_entries}"

        # Verify "tunnel:culvert" entries are present
        culvert_entries = result.html_content.count("tunnel:</i> culvert")
        assert (
            culvert_entries >= 2
        ), f"Expected at least 2 tunnel:culvert entries, found {culvert_entries}"

        # Test comparison: without --include-waterways should have fewer brunnels
        default_result = run_brunnels_cli(gpx_file)
        assert default_result.exit_code == 0

        assert (
            result.metrics["total_brunnels_found"]
            > default_result.metrics["total_brunnels_found"]
        ), "Including waterways should increase total brunnels found"

        assert (
            result.metrics["final_included_total"]
            >= default_result.metrics["final_included_total"]
        ), "Including waterways should not decrease final included brunnels"


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

    @pytest.mark.skipif(os.getenv("CI") == "true", reason="Skip in CI environment")
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

        # Should contain the "No brunnels found" message
        assert "No nearby brunnels found" in result.stdout

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

    def test_overlap_exclusion_with_increased_buffer(
        self, gpx_file: Path, metadata: Dict[str, Any]
    ):
        """Test overlap exclusion with increased route buffer (key feature of this route)"""
        # Test with route_buffer=5.0 (required to detect overlapping brunnels)
        result = run_brunnels_cli(gpx_file, route_buffer=5.0)
        assert result.exit_code == 0

        # Should have overlap exclusion active (now always enabled)
        assert "alternative" in result.exclusion_details
        overlap_excluded = result.exclusion_details["alternative"]
        assert (
            overlap_excluded >= 1
        ), f"Expected >=1 overlap excluded, got {overlap_excluded}"

    def test_known_bridges_present(self, gpx_file: Path, metadata: Dict[str, Any]):
        """Test that known bridges are detected correctly"""
        result = run_brunnels_cli(gpx_file, route_buffer=5.0)  # Use increased buffer
        assert result.exit_code == 0

        self.assert_known_bridges_present(result, metadata)

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

    @pytest.mark.skipif(os.getenv("CI") == "true", reason="Skip in CI environment")
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
            b
            for b in result.included_brunnels
            if not b.get("name", "").startswith("<OSM ")
        ]
        unnamed_bridges = [
            b for b in result.included_brunnels if b.get("name", "").startswith("<OSM ")
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

    def test_bearing_alignment_exclusion(
        self, gpx_file: Path, metadata: Dict[str, Any]
    ):
        """Test bearing alignment exclusion effectiveness"""
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

        # Check that some brunnels were excluded for bearing misalignment
        if "misaligned" in default_result.exclusion_details:
            assert (
                default_result.exclusion_details["misaligned"] >= 3
            ), "Expected some bearing misalignment exclusion"


class TestAcrossAmericaRoute(BaseRouteTest):
    """Integration tests for AcrossAmerica transcontinental route"""

    @pytest.fixture
    def metadata(self, gpx_file: Path) -> Dict[str, Any]:
        """Load metadata JSON file matching the GPX basename"""
        metadata_file = gpx_file.with_suffix(".json")
        with open(metadata_file) as f:
            return json.load(f)

    @pytest.fixture
    def gpx_file(self) -> Path:
        """Path to AcrossAmerica GPX file"""
        return Path(__file__).parent / "fixtures" / "AcrossAmerica.gpx"

    def test_known_bridges_present(
        self, default_result: BrunnelsTestResult, metadata: Dict[str, Any]
    ):
        """Test that known bridges are detected correctly"""
        result = default_result
        assert result.exit_code == 0

        self.assert_known_bridges_present(result, metadata)

    def test_transcontinental_chunking(
        self, default_result: BrunnelsTestResult, metadata: Dict[str, Any]
    ):
        """Test that long transcontinental route is processed in chunks"""
        result = default_result
        assert result.exit_code == 0

        # Should have processed route in chunks (indicated by chunked query messages)
        assert "chunks for Overpass queries" in result.stderr
        assert "Chunk 1/9" in result.stderr
        assert "Chunk 9/9" in result.stderr

        # Should have significant route distance
        assert result.metrics["total_distance_km"] > 4500
        assert result.metrics["track_points"] > 40000

    def test_compound_bridge_detection(
        self, default_result: BrunnelsTestResult, metadata: Dict[str, Any]
    ):
        """Test that compound bridges are detected correctly"""
        result = default_result
        assert result.exit_code == 0

        # Should have 4 compound bridges
        compound_brunnels = [
            b for b in result.included_brunnels if b["type"] == "compound"
        ]
        assert (
            len(compound_brunnels) == 4
        ), f"Expected 4 compound bridges, found {len(compound_brunnels)}"

        # Verify each compound bridge has 2 segments
        for compound in compound_brunnels:
            assert (
                compound["segments"] == 2
            ), f"Expected 2 segments for compound bridge {compound['name']}"

    def test_overlap_exclusion(
        self, default_result: BrunnelsTestResult, metadata: Dict[str, Any]
    ):
        """Test that overlap exclusion works correctly"""
        result = default_result
        assert result.exit_code == 0

        # Should have 1 overlap exclusion
        assert "alternative" in result.exclusion_details
        assert result.exclusion_details["alternative"] == 1

    def test_no_tunnels_detected(
        self, default_result: BrunnelsTestResult, metadata: Dict[str, Any]
    ):
        """Test that no tunnels are detected along this route"""
        result = default_result
        assert result.exit_code == 0

        # Should have 0 tunnels
        assert result.metrics["contained_tunnels"] == 0
        tunnel_brunnels = [
            b for b in result.included_brunnels if b["brunnel_type"] == "tunnel"
        ]
        assert len(tunnel_brunnels) == 0

    def test_transcontinental_performance(
        self, default_result: BrunnelsTestResult, metadata: Dict[str, Any]
    ):
        """Test performance with transcontinental route"""
        result = default_result
        assert result.exit_code == 0

        # Use the processing time captured during fixture creation
        processing_time = result.processing_time
        benchmarks = metadata["performance_benchmarks"]

        # Parse expected time range
        time_range = benchmarks["processing_time_seconds"]
        min_time, max_time = map(int, time_range.split("-"))

        # Note: Don't fail in CI, just report the timing
        if os.getenv("CI") == "true":
            print(
                f"CI processing time: {processing_time:.1f}s (benchmark: {time_range}s)"
            )
        else:
            assert (
                processing_time <= max_time
            ), f"Processing took {processing_time:.1f}s, expected <{max_time}s"

    def test_major_highway_bridges(
        self, default_result: BrunnelsTestResult, metadata: Dict[str, Any]
    ):
        """Test that major highway bridges are detected"""
        result = default_result
        assert result.exit_code == 0

        # Check for major highway bridges by name
        highway_names = [
            "United States Highway 160",
            "Highway Of Legends",
            "James A. Rhodes Appalachian Highway",
            "National Pike",
        ]

        included_names = {b["name"] for b in result.included_brunnels}

        for highway_name in highway_names:
            found = any(highway_name in name for name in included_names)
            assert found, f"Major highway bridge '{highway_name}' not found"

    def test_bearing_alignment_exclusion(
        self, gpx_file: Path, metadata: Dict[str, Any]
    ):
        """Test bearing alignment exclusion on transcontinental route"""
        # Test with default tolerance (cached)
        default_result = run_brunnels_cli(gpx_file)
        assert default_result.exit_code == 0

        # Test with strict tolerance (cached)
        strict_result = run_brunnels_cli(gpx_file, bearing_tolerance=2.0)
        assert strict_result.exit_code == 0

        # Stricter tolerance should result in same or fewer included brunnels
        assert (
            strict_result.metrics["final_included_total"]
            <= default_result.metrics["final_included_total"]
        ), "Stricter bearing tolerance should not increase included brunnels"

        # Should have some misalignment exclusion with default tolerance (but much less than with strict)
        default_misaligned = default_result.exclusion_details.get("misaligned", 0)
        strict_misaligned = strict_result.exclusion_details.get("misaligned", 0)

        # Strict tolerance should exclude more bridges for misalignment
        assert (
            strict_misaligned >= default_misaligned
        ), "Stricter bearing tolerance should increase misaligned exclusions"
        assert (
            strict_misaligned >= 5
        ), f"Expected >=5 misaligned bridges with strict tolerance, got {strict_misaligned}"


class TestChehalisRoute(BaseRouteTest):
    """Integration tests for Chehalis Western Trail (railway=razed tags)"""

    @pytest.fixture
    def metadata(self, gpx_file: Path) -> Dict[str, Any]:
        """Load metadata JSON file matching the GPX basename"""
        metadata_file = gpx_file.with_suffix(".json")
        with open(metadata_file) as f:
            return json.load(f)

    @pytest.fixture
    def gpx_file(self) -> Path:
        """Path to Chehalis GPX file"""
        return Path(__file__).parent / "fixtures" / "Chehalis.gpx"

    def test_known_bridges_and_tunnels_present(
        self, gpx_file: Path, metadata: Dict[str, Any]
    ):
        """Test that known bridges and tunnels are detected correctly"""
        result = run_brunnels_cli(gpx_file)
        assert result.exit_code == 0

        self.assert_known_infrastructure_present(result, metadata)

    def test_railway_razed_tags_in_html(self, gpx_file: Path):
        """Test that railway=razed tags appear in HTML popups (not highlighted in red)"""
        result = run_brunnels_cli(gpx_file)
        assert result.exit_code == 0
        assert result.html_content is not None

        html_content = result.html_content

        # Should contain railway=razed tags (not highlighted in red)
        railway_razed_count = html_content.count("<i>railway:</i> razed")
        assert (
            railway_razed_count >= 2
        ), f"Expected >=2 railway=razed tags, found {railway_razed_count}"

        # railway=razed should NOT be highlighted in red (verify it's not in red spans)
        railway_razed_highlighted = html_content.count(
            "<span style='color: red;'><i>railway:</i> razed"
        )
        assert (
            railway_razed_highlighted == 0
        ), f"railway=razed should not be highlighted in red, found {railway_razed_highlighted}"

        # Verify railway=abandoned is not highlighted either (should be in some bridges)
        railway_abandoned_highlighted = html_content.count(
            "<span style='color: red;'><i>railway:</i> abandoned"
        )
        assert (
            railway_abandoned_highlighted == 0
        ), f"railway=abandoned should not be highlighted in red, found {railway_abandoned_highlighted}"

    def test_highway_cycleway_tags_in_html(self, gpx_file: Path):
        """Test that highway=cycleway tags appear in HTML popups"""
        result = run_brunnels_cli(gpx_file)
        assert result.exit_code == 0
        assert result.html_content is not None

        html_content = result.html_content

        # Should contain highway=cycleway tags (all bridges and the tunnel have this)
        highway_cycleway_count = html_content.count("<i>highway:</i> cycleway")
        assert (
            highway_cycleway_count >= 6
        ), f"Expected >=6 highway=cycleway tags, found {highway_cycleway_count}"

        # highway=cycleway should NOT be highlighted in red
        highway_cycleway_highlighted = html_content.count(
            "<span style='color: red;'><i>highway:</i> cycleway"
        )
        assert (
            highway_cycleway_highlighted == 0
        ), f"highway=cycleway should not be highlighted in red, found {highway_cycleway_highlighted}"

    def test_rails_to_trails_characteristics(
        self, gpx_file: Path, metadata: Dict[str, Any]
    ):
        """Test characteristics specific to rails-to-trails conversion"""
        result = run_brunnels_cli(gpx_file)
        assert result.exit_code == 0

        # All included brunnels should have the same name (Chehalis Western Trail)
        trail_name_count = sum(
            1
            for b in result.included_brunnels
            if "Chehalis Western Trail" in b.get("name", "")
        )
        assert trail_name_count == len(
            result.included_brunnels
        ), "All brunnels should be part of Chehalis Western Trail"

        # Should have good mix of bridges and tunnels
        bridge_count = sum(
            1 for b in result.included_brunnels if b.get("brunnel_type") == "bridge"
        )
        tunnel_count = sum(
            1 for b in result.included_brunnels if b.get("brunnel_type") == "tunnel"
        )

        assert bridge_count == 5, f"Expected 5 bridges, found {bridge_count}"
        assert tunnel_count == 1, f"Expected 1 tunnel, found {tunnel_count}"

        # All brunnels should be individual (no compound brunnels expected)
        individual_count = sum(
            1 for b in result.included_brunnels if b.get("type") == "individual"
        )
        assert individual_count == len(
            result.included_brunnels
        ), "All brunnels should be individual"


class TestCoronadoRoute(BaseRouteTest):
    """Integration tests for Coronado Bay Trail"""

    @pytest.fixture
    def metadata(self, gpx_file: Path) -> Dict[str, Any]:
        """Load metadata JSON file matching the GPX basename"""
        metadata_file = gpx_file.with_suffix(".json")
        with open(metadata_file) as f:
            return json.load(f)

    @pytest.fixture
    def gpx_file(self) -> Path:
        """Path to Coronado GPX file"""
        return Path(__file__).parent / "fixtures" / "Coronado.gpx"

    def test_known_bridges_present(self, gpx_file: Path, metadata: Dict[str, Any]):
        """Test that known bridges are detected correctly"""
        result = run_brunnels_cli(gpx_file)
        assert result.exit_code == 0

        self.assert_known_bridges_present(result, metadata)

    def test_bearing_alignment_exclusion(self, gpx_file: Path):
        """Test that bearing misalignment exclusion works correctly"""
        result = run_brunnels_cli(gpx_file)
        assert result.exit_code == 0

        # With improved alignment algorithm, no bridges should be excluded for misalignment
        assert (
            result.exclusion_details.get("misaligned", 0) == 0
        ), f"Expected 0 bearing misalignment, got {result.exclusion_details.get('misaligned', 0)}"

        # Test with stricter bearing tolerance should filter more
        strict_result = run_brunnels_cli(gpx_file, bearing_tolerance=10.0)
        assert strict_result.exit_code == 0

        # Should have same or fewer included bridges with stricter tolerance
        assert (
            strict_result.metrics["final_included_total"]
            <= result.metrics["final_included_total"]
        )

    def test_include_bicycle_infrastructure(
        self, gpx_file: Path, metadata: Dict[str, Any]
    ):
        """Test that --include-bicycle-no flag reveals additional infrastructure"""
        # Test with bicycle infrastructure included
        result = run_brunnels_cli(gpx_file, route_buffer=5.0, include_bicycle_no=True)
        assert result.exit_code == 0

        # Should find significantly more brunnels
        assert result.metrics["total_brunnels_found"] == 193
        assert result.metrics["total_bridges_found"] == 178
        assert result.metrics["total_tunnels_found"] == 14

        # Should include compound bridge and tunnel
        assert result.metrics["final_included_total"] == 9
        assert result.metrics["final_included_individual"] == 8
        assert result.metrics["final_included_compound"] == 1
        assert result.metrics["contained_bridges"] == 8
        assert result.metrics["contained_tunnels"] == 1

        # Check default bridges are still found using helper method
        result.assert_bridges_found(
            metadata["known_bridges"], "with bicycle infrastructure"
        )

        # Get OSM IDs and names for bicycle infrastructure checks
        included_osm_ids, included_names = result.get_included_identifiers()

        # Check bicycle infrastructure bridges (by name or OSM ID)
        for bridge in metadata["known_bridges_bicycle_infrastructure"]:
            if "osm_way_ids" in bridge:
                # Compound bridge - check if components are found (by name or OSM ID)
                bridge_ids = {str(oid) for oid in bridge["osm_way_ids"]}
                found_ids = bridge_ids & included_osm_ids
                # For compound bridges, check if the bridge name appears in any of the included names
                name_found = any(bridge["name"] in name for name in included_names)
                bridge_found = len(found_ids) > 0 or name_found
                assert (
                    bridge_found
                ), f"Bicycle infrastructure compound bridge {bridge['name']} components not found"
            else:
                bridge_found = (
                    str(bridge["osm_way_id"]) in included_osm_ids
                    or bridge["name"] in included_names
                )
                assert (
                    bridge_found
                ), f"Bicycle infrastructure bridge {bridge['name']} (OSM {bridge['osm_way_id']}) not found"

        # Check bicycle infrastructure tunnels (by name or OSM ID)
        for tunnel in metadata["known_tunnels_bicycle_infrastructure"]:
            tunnel_found = (
                str(tunnel["osm_way_id"]) in included_osm_ids
                or tunnel["name"] in included_names
            )
            assert (
                tunnel_found
            ), f"Bicycle infrastructure tunnel {tunnel['name']} (OSM {tunnel['osm_way_id']}) not found"

        # Compare with default settings - should find more
        default_result = run_brunnels_cli(gpx_file)
        assert (
            result.metrics["total_brunnels_found"]
            > default_result.metrics["total_brunnels_found"]
        ), "Including bicycle infrastructure should find more brunnels"


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

    print("\n=== Exclusion Details ===")
    # Assuming 'expected["filtered_brunnels"]' key from JSON is stable for this subtask for debug_route
    exclusion_expected_json_data = expected["filtered_brunnels"]
    print(
        f"Total excluded: {result.exclusion_details.get('total', 'N/A')} (expected: {exclusion_expected_json_data['total']})"
    )

    print("\n=== Individual Exclusion Reasons ===")
    for reason, expected_range in exclusion_expected_json_data.items():
        if reason != "total":
            actual = result.exclusion_details.get(reason, "N/A")
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
