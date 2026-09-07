"""Tests for the Biketerra brunnels server source."""

import argparse
from pathlib import Path

import pytest

from brunnels.biketerra import (
    MAX_COORDS_PER_REQUEST,
    SERVER_QUERY_BUFFER,
    _chunk_coords,
    unsupported_options,
)
from brunnels.geometry import Position

from .test_integration import run_brunnels_cli

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def make_args(**overrides) -> argparse.Namespace:
    """Build an args namespace with the CLI defaults for the options we check."""
    defaults = dict(
        include_waterways=False,
        include_bicycle_no=False,
        include_active_railways=False,
        query_buffer=10.0,
    )
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


class TestUnsupportedOptions:
    """The server applies fixed filtering, so some options force Overpass."""

    def test_defaults_are_supported(self):
        assert unsupported_options(make_args()) == []

    @pytest.mark.parametrize(
        "option,flag",
        [
            ("include_waterways", "--include-waterways"),
            ("include_bicycle_no", "--include-bicycle-no"),
            ("include_active_railways", "--include-active-railways"),
        ],
    )
    def test_include_flags_are_unsupported(self, option, flag):
        assert unsupported_options(make_args(**{option: True})) == [flag]

    def test_query_buffer_within_server_corridor_is_supported(self):
        assert unsupported_options(make_args(query_buffer=SERVER_QUERY_BUFFER)) == []

    def test_wider_query_buffer_is_unsupported(self):
        unsupported = unsupported_options(
            make_args(query_buffer=SERVER_QUERY_BUFFER + 1)
        )
        assert len(unsupported) == 1
        assert unsupported[0].startswith("--query-buffer")


class TestChunkCoords:
    """The server rejects requests over MAX_COORDS_PER_REQUEST points."""

    @staticmethod
    def make_coords(n):
        return [Position(latitude=45.0 + i / 100000.0, longitude=7.0) for i in range(n)]

    def test_short_route_is_one_chunk(self):
        chunks = _chunk_coords(self.make_coords(100))
        assert len(chunks) == 1
        assert len(chunks[0]) == 100

    def test_route_at_the_limit_is_one_chunk(self):
        chunks = _chunk_coords(self.make_coords(MAX_COORDS_PER_REQUEST))
        assert len(chunks) == 1

    @pytest.mark.parametrize(
        "n", [MAX_COORDS_PER_REQUEST + 1, MAX_COORDS_PER_REQUEST * 3, 20000]
    )
    def test_long_route_is_split_within_the_limit(self, n):
        coords = self.make_coords(n)
        chunks = _chunk_coords(coords)

        assert all(len(chunk) <= MAX_COORDS_PER_REQUEST for chunk in chunks)
        assert all(len(chunk) >= 2 for chunk in chunks)

        # Chunks overlap by one point, so every segment of the route is covered
        # by exactly one request.
        rejoined = chunks[0][:]
        for chunk in chunks[1:]:
            assert chunk[0] == rejoined[-1]
            rejoined.extend(chunk[1:])
        assert rejoined == [[c.latitude, c.longitude] for c in coords]


class TestSourceSelection:
    """End-to-end checks that the two sources agree on what's on the route."""

    @pytest.fixture(scope="class")
    def gpx_file(self):
        return FIXTURES_DIR / "Chehalis.gpx"

    def test_biketerra_is_the_default_source(self, gpx_file):
        result = run_brunnels_cli(gpx_file, source="auto")
        assert result.exit_code == 0
        assert "Querying Biketerra server" in result.stderr

    def test_biketerra_matches_overpass_included_brunnels(self, gpx_file):
        biketerra = run_brunnels_cli(gpx_file, source="biketerra")
        overpass = run_brunnels_cli(gpx_file, source="overpass")

        assert biketerra.exit_code == 0
        assert overpass.exit_code == 0

        biketerra_ids, biketerra_names = biketerra.get_included_identifiers()
        overpass_ids, overpass_names = overpass.get_included_identifiers()

        assert biketerra_ids == overpass_ids
        assert biketerra_names == overpass_names

    def test_biketerra_returns_fewer_candidates_than_overpass(self, gpx_file):
        """The server filters to the route corridor; Overpass returns the bbox."""
        biketerra = run_brunnels_cli(gpx_file, source="biketerra")
        overpass = run_brunnels_cli(gpx_file, source="overpass")

        assert (
            biketerra.metrics["total_brunnels_found"]
            <= overpass.metrics["total_brunnels_found"]
        )

    def test_include_flag_rejected_with_explicit_biketerra_source(self, gpx_file):
        result = run_brunnels_cli(gpx_file, source="biketerra", include_waterways=True)
        assert result.exit_code != 0
        assert "--include-waterways" in result.stderr

    def test_include_flag_falls_back_to_overpass(self, gpx_file):
        result = run_brunnels_cli(gpx_file, source="auto", include_waterways=True)
        assert result.exit_code == 0
        assert "Using Overpass API" in result.stderr
