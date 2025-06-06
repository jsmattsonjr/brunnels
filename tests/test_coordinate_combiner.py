import pytest

from brunnels.coordinate_combiner import DirectionalCoordinateCombiner
from brunnels.brunnel_way import BrunnelWay
from brunnels.geometry import Position
from brunnels.brunnel import BrunnelType


def create_mock_way(
    id_val,
    nodes: list[int],
    coords: list[Position],
    brunnel_type_val: BrunnelType = BrunnelType.BRIDGE,
) -> BrunnelWay:
    """Helper function to create a BrunnelWay instance for testing."""
    metadata = {"id": id_val, "nodes": nodes}
    return BrunnelWay(coords=coords, metadata=metadata, brunnel_type=brunnel_type_val)


@pytest.fixture
def combiner():
    return DirectionalCoordinateCombiner([])


def test_no_components(combiner):
    """Test combining an empty list of components."""
    combiner.components = []
    result = combiner.combine_coordinates()
    assert result == []


def test_single_component(combiner):
    """Test combining a single component."""
    way1 = create_mock_way(1, [10, 20], [Position(0, 0), Position(0, 1)])
    combiner.components = [way1]
    result = combiner.combine_coordinates()
    assert result == [Position(0, 0), Position(0, 1)]


def test_two_components_forward_forward():
    """Test combining two components, both forward."""
    p1, p2, p3 = Position(0, 0), Position(0, 1), Position(0, 2)
    way1 = create_mock_way(1, [10, 20], [p1, p2])
    way2 = create_mock_way(2, [20, 30], [p2, p3])
    local_combiner = DirectionalCoordinateCombiner([way1, way2])
    result = local_combiner.combine_coordinates()
    assert result == [p1, p2, p3]


def test_three_components_mixed_directions():
    """Test combining three components with mixed directions."""
    p1, p2, p3, p4 = Position(0, 0), Position(0, 1), Position(0, 2), Position(0, 3)
    way1 = create_mock_way(1, [10, 20], [p1, p2])  # Fwd: 10-20 (p1-p2)
    way2 = create_mock_way(
        2, [30, 20], [p3, p2]
    )  # Bwd: 30-20 (p3-p2) -> Joins p2 of way1
    way3 = create_mock_way(
        3, [30, 40], [p3, p4]
    )  # Fwd: 30-40 (p3-p4) -> Joins p3 of (reversed) way2
    local_combiner = DirectionalCoordinateCombiner([way1, way2, way3])
    result = local_combiner.combine_coordinates()
    assert result == [p1, p2, p3, p4]


def test_invalid_connection_no_shared_node():
    """Test error when two components share no nodes."""
    p1, p2, p3, p4 = Position(0, 0), Position(0, 1), Position(0, 2), Position(0, 3)
    way1 = create_mock_way(1, [10, 20], [p1, p2])
    way2 = create_mock_way(2, [30, 40], [p3, p4])
    with pytest.raises(ValueError, match="don't share exactly one node"):
        DirectionalCoordinateCombiner([way1, way2])


def test_invalid_connection_multiple_shared_nodes():
    """Test error when two components share multiple nodes."""
    p1, p2, p3, p4 = Position(0, 0), Position(0, 1), Position(0, 2), Position(0, 3)
    way1 = create_mock_way(1, [10, 20, 30], [p1, p2, p3])
    way2 = create_mock_way(2, [20, 30, 40], [p2, p3, p4])
    with pytest.raises(ValueError, match="don't share exactly one node"):
        DirectionalCoordinateCombiner([way1, way2])


def test_invalid_internal_component_connection_same_endpoint():
    """Test error when a component tries to use the same endpoint for two connections."""
    p1, p2, p3, p4 = Position(0, 0), Position(0, 1), Position(0, 2), Position(0, 3)
    way1 = create_mock_way(1, [10, 20], [p1, p2])
    way2 = create_mock_way(
        2, [20, 30], [p2, p3]
    )  # Connects to way1 via node 20 (way2's first)
    way3 = create_mock_way(
        3, [20, 40], [p2, p4]
    )  # Connects to way2 via node 20 (way2's first again)
    with pytest.raises(ValueError, match="uses same endpoint"):
        DirectionalCoordinateCombiner([way1, way2, way3])


def test_invalid_connection_shared_node_not_at_endpoint1():
    """Test error when shared node is not at an endpoint of the first way."""
    p1, p2, p3 = Position(0, 0), Position(0, 1), Position(0, 2)
    p_extra = Position(0, 3)
    way1 = create_mock_way(1, [10, 20, 50], [p1, p2, p_extra])  # node 20 is internal
    way2 = create_mock_way(2, [20, 30], [p2, p3])
    with pytest.raises(ValueError, match="don't share exactly one node"):
        DirectionalCoordinateCombiner([way1, way2])


def test_invalid_connection_shared_node_not_at_endpoint2():
    """Test error when shared node is not at an endpoint of the second way."""
    p1, p2, p3 = Position(0, 0), Position(0, 1), Position(0, 2)
    p_extra = Position(0, 3)
    way1 = create_mock_way(1, [10, 20], [p1, p2])
    way2 = create_mock_way(2, [30, 20, 40], [p3, p2, p_extra])  # node 20 is internal
    with pytest.raises(ValueError, match="don't share exactly one node"):
        DirectionalCoordinateCombiner([way1, way2])


def test_two_components_forward_backward():
    """Test combining two components, forward then backward."""
    p1, p2, p3 = Position(0, 0), Position(0, 1), Position(0, 2)
    way1 = create_mock_way(1, [10, 20], [p1, p2])
    way2 = create_mock_way(2, [30, 20], [p3, p2])  # Note: nodes and coords reversed
    local_combiner = DirectionalCoordinateCombiner([way1, way2])
    result = local_combiner.combine_coordinates()
    assert result == [p1, p2, p3]


def test_two_components_backward_forward():
    """Test combining two components, backward then forward."""
    p1, p2, p3 = Position(0, 0), Position(0, 1), Position(0, 2)
    way1 = create_mock_way(1, [20, 10], [p2, p1])
    way2 = create_mock_way(2, [20, 30], [p2, p3])
    local_combiner = DirectionalCoordinateCombiner([way1, way2])
    result = local_combiner.combine_coordinates()
    assert result == [p1, p2, p3]


def test_two_components_backward_backward():
    """Test combining two components, both backward."""
    p1, p2, p3 = Position(0, 0), Position(0, 1), Position(0, 2)
    way1 = create_mock_way(1, [20, 10], [p2, p1])
    way2 = create_mock_way(2, [30, 20], [p3, p2])
    local_combiner = DirectionalCoordinateCombiner([way1, way2])
    result = local_combiner.combine_coordinates()
    assert result == [p1, p2, p3]
