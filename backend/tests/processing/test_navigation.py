from app.processing.navigation import a_star

SIMPLE_GRAPH = {
    1: {"neighbors": [(2, 1.0), (3, 5.0)], "pos": (0.0, 0.0)},
    2: {"neighbors": [(1, 1.0), (3, 1.0)], "pos": (1.0, 0.0)},
    3: {"neighbors": [(2, 1.0), (1, 5.0)], "pos": (2.0, 0.0)},
}


def test_a_star_simple_graph_returns_path():
    path = a_star(SIMPLE_GRAPH, start_id=1, end_id=3)
    assert path is not None
    assert path[0] == 1 and path[-1] == 3, "Path must start at 1 and end at 3"
    assert path == [1, 2, 3], "Optimal path: 1->2->3 (cost=2.0)"


def test_a_star_disconnected_graph_returns_none():
    graph = {
        1: {"neighbors": [], "pos": (0.0, 0.0)},
        2: {"neighbors": [], "pos": (1.0, 0.0)},
    }
    result = a_star(graph, start_id=1, end_id=2)
    assert result is None, "Disconnected graph should return None"
