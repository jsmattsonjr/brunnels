import pytest

from src.brunnels.geometry import Position
from src.brunnels.route import Route


def test_route_creation_and_basic_properties():
    """
    Tests basic Route creation, coordinate storage, length, indexing, and iteration.
    """
    # 1. Create a few Position objects
    pos1 = Position(latitude=10.0, longitude=20.0, elevation=5.0)
    pos2 = Position(latitude=10.1, longitude=20.1, elevation=10.0)
    pos3 = Position(latitude=10.2, longitude=20.2, elevation=15.0)
    my_position_list = [pos1, pos2, pos3]

    # 2. Create a Route object using these Position objects
    route = Route(coords=my_position_list)

    # 3. Assert that route.coords is the same as my_position_list
    assert route.coords == my_position_list, "Route.coords should store the input list of positions."

    # 4. Assert that len(route) returns the correct number of positions
    assert len(route) == len(my_position_list), "len(route) should return the number of coordinates."
    assert len(route) == 3, "len(route) should be 3 for the given test data."

    # 5. Assert that accessing an element (e.g., route[0]) returns the correct Position object
    assert route[0] == pos1, "Indexing route[0] should return the first Position object."
    assert route[1] == pos2, "Indexing route[1] should return the second Position object."
    assert route[-1] == pos3, "Indexing route[-1] should return the last Position object."

    # 6. Assert that iterating over route yields the Position objects
    iterated_positions = []
    for pos in route:
        iterated_positions.append(pos)
    assert iterated_positions == my_position_list, "Iterating over the route should yield the original Position objects in order."

    # Test with an empty list of positions
    empty_route = Route(coords=[])
    assert len(empty_route) == 0, "len(route) should be 0 for an empty coordinate list."
    assert empty_route.coords == [], "Route.coords should be an empty list for an empty input."

    # Test with a single position
    single_pos_list = [pos1]
    single_pos_route = Route(coords=single_pos_list)
    assert len(single_pos_route) == 1, "len(route) should be 1 for a single coordinate."
    assert single_pos_route.coords == single_pos_list
    assert single_pos_route[0] == pos1

    iterated_single = []
    for pos in single_pos_route:
        iterated_single.append(pos)
    assert iterated_single == single_pos_list

def test_route_coordinate_list_property():
    """
    Tests the coordinate_list property of the Route class.
    """
    pos1 = Position(latitude=10.0, longitude=20.0, elevation=5.0)
    pos2 = Position(latitude=10.1, longitude=20.1, elevation=10.0)
    my_position_list = [pos1, pos2]

    route = Route(coords=my_position_list)

    # The coordinate_list property should return the same list as .coords
    assert route.coordinate_list == my_position_list
    assert route.coordinate_list is route.coords, "coordinate_list should return a direct reference to coords."

    empty_route = Route(coords=[])
    assert empty_route.coordinate_list == []

def test_route_from_positions_constructor():
    """
    Tests the Route.from_positions class method.
    """
    pos1 = Position(latitude=30.0, longitude=40.0, elevation=100.0)
    pos2 = Position(latitude=30.1, longitude=40.1, elevation=105.0)
    my_positions = [pos1, pos2]

    route = Route.from_positions(my_positions)

    assert route.coords == my_positions
    assert len(route) == 2
    assert route[0] == pos1

    # Test with empty list
    empty_route = Route.from_positions([])
    assert len(empty_route) == 0
    assert empty_route.coords == []

    # Test with Position objects that might cause issues (e.g. near poles, antimeridian - though _check_route handles this)
    # This specific test focuses on construction, _check_route has its own tests (implicitly via from_gpx)
    # or would need dedicated tests if we wanted to unit test _check_route directly with various Position lists.
    # For now, assume valid positions for basic construction test.

def test_route_constructor_default_cumulative_distance():
    """
    Tests that cumulative_distance is initialized as an empty list by default
    if not provided, as per the dataclass definition.
    """
    pos1 = Position(latitude=10.0, longitude=20.0)
    route_minimal = Route(coords=[pos1])
    # The actual calculation of cumulative_distance is done by calculate_distances()
    # Here we only check that the field is initialized.
    # Before calculate_distances() is called, it should be empty as per init=False and default_factory=list
    # However, the current implementation of calculate_distances() in the provided code
    # initializes it to a list of zeros *matching the length of trackpoints/coords*.
    # The prompt implies testing the direct Route construction.
    # Let's stick to the dataclass definition: default_factory=list, init=False.
    # This means it will be an empty list *until* calculate_distances is called.
    # The previous subtask updated calculate_distances to initialize:
    # self.cumulative_distance = [0.0] * len(self.coords)
    # So, after Route(coords=...) and *before* calculate_distances(), it should be empty.
    # This seems like a slight mismatch with how calculate_distances immediately populates it.
    # For the purpose of this test, I'll test the state *after* Route() call.
    # The dataclass field definition `cumulative_distance: List[float] = field(default_factory=list, init=False)`
    # means that if `calculate_distances` is NOT called, it would be `[]`.
    # Let's assume the test is for a "fresh" Route object.
    assert route_minimal.cumulative_distance == [], \
        "cumulative_distance should be an empty list on Route initialization before calculate_distances()"

    # If the intention is to test *after* calculate_distances would normally run (e.g. in from_gpx),
    # that would be a different test. This test is for the raw dataclass behavior.
    # However, many methods like `closest_point_to` *rely* on `cumulative_distance` being populated.
    # The `Route.from_gpx` and `Route.from_file` call `calculate_distances`.
    # `Route.from_positions` also calls `_check_route` but not `calculate_distances`.
    # This might be an area for future clarification in the main codebase.
    # For now, testing the direct constructor.

    # If we consider that calculate_distances is an integral part of making a Route "usable"
    # for many of its methods, one might argue it should be called in __post_init__.
    # But sticking to the current structure:
    route_two_coords = Route(coords=[pos1, Position(1,1)])
    assert route_two_coords.cumulative_distance == []

    # If calculate_distances was called:
    # route_two_coords.calculate_distances()
    # assert route_two_coords.cumulative_distance == [0.0, some_distance_value]
    # But this test is about the initial state.
