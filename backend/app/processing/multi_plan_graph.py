"""
Pure helpers for assembling and routing across multiple reconstruction graphs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import networkx as nx


@dataclass(frozen=True)
class PlanData:
    reconstruction_id: int
    graph: nx.Graph
    mask_width: int
    mask_height: int
    scale_factor: float


@dataclass(frozen=True)
class TransitionPointData:
    id: int
    reconstruction_id: int
    group_id: int
    x_norm: float
    y_norm: float


@dataclass(frozen=True)
class GroupData:
    id: int
    type: str


@dataclass(frozen=True)
class PlanMetadata:
    mask_width: int
    mask_height: int
    scale_factor: float


@dataclass(frozen=True)
class RouteSegmentData:
    reconstruction_id: int
    coordinates: list[list[float]]
    transition_out_point_id: int | None


@dataclass(frozen=True)
class MultiPlanRouteResultData:
    status: str
    message: str | None
    total_distance_meters: float | None
    segments: list[RouteSegmentData]


def snap_to_graph(G: nx.Graph, x_px: float, y_px: float, radius_px: float) -> str | int | None:
    nearest_node_id: str | int | None = None
    nearest_distance = radius_px
    for node_id, data in G.nodes(data=True):
        pos = data.get("pos")
        if not pos:
            continue
        node_type = data.get("type")
        if node_type not in {"corridor_node", "door", "corridor_entry", "room"}:
            continue
        distance = ((pos[0] - x_px) ** 2 + (pos[1] - y_px) ** 2) ** 0.5
        if distance <= nearest_distance:
            nearest_distance = distance
            nearest_node_id = node_id
    return nearest_node_id


def build_super_graph(
    plan_data: list[PlanData],
    transition_points: list[TransitionPointData],
    group_edge_weight: Callable[[GroupData], float] = lambda _group: 0.0,
) -> tuple[nx.Graph, dict[int, str]]:
    super_graph = nx.Graph()
    point_node_map: dict[int, str] = {}

    for plan in plan_data:
        prefix = f"plan_{plan.reconstruction_id}_"
        for node_id, data in plan.graph.nodes(data=True):
            super_graph.add_node(f"{prefix}{node_id}", **data)
        for source, target, data in plan.graph.edges(data=True):
            super_graph.add_edge(
                f"{prefix}{source}",
                f"{prefix}{target}",
                **data,
            )

    plan_lookup = {plan.reconstruction_id: plan for plan in plan_data}
    plan_graph_lookup = {plan.reconstruction_id: plan.graph for plan in plan_data}

    group_lookup: dict[int, list[TransitionPointData]] = {}
    for point in transition_points:
        group_lookup.setdefault(point.group_id, []).append(point)

    for point in transition_points:
        plan = plan_lookup.get(point.reconstruction_id)
        if plan is None:
            continue
        graph = plan_graph_lookup[point.reconstruction_id]
        x_px = point.x_norm * plan.mask_width
        y_px = point.y_norm * plan.mask_height
        snapped_node_id = snap_to_graph(graph, x_px, y_px, radius_px=max(plan.mask_width, plan.mask_height) * 0.15)
        if snapped_node_id is None:
            continue
        transition_node_id = f"transition_{point.id}"
        point_node_map[point.id] = transition_node_id
        super_graph.add_node(
            transition_node_id,
            type="transition",
            pos=(x_px, y_px),
            reconstruction_id=point.reconstruction_id,
            transition_point_id=point.id,
        )
        prefixed_snap = f"plan_{point.reconstruction_id}_{snapped_node_id}"
        weight = ((x_px - plan.graph.nodes[snapped_node_id]["pos"][0]) ** 2 + (y_px - plan.graph.nodes[snapped_node_id]["pos"][1]) ** 2) ** 0.5 * plan.scale_factor
        super_graph.add_edge(transition_node_id, prefixed_snap, weight=weight)

    for group_id, points in group_lookup.items():
        group = GroupData(id=group_id, type="passage")
        edge_weight = group_edge_weight(group)
        for left_index in range(len(points)):
            for right_index in range(left_index + 1, len(points)):
                left_node = point_node_map.get(points[left_index].id)
                right_node = point_node_map.get(points[right_index].id)
                if left_node is None or right_node is None:
                    continue
                super_graph.add_edge(left_node, right_node, weight=edge_weight)

    return super_graph, point_node_map


def find_multi_plan_route(
    G_super: nx.Graph,
    from_node_id: str,
    to_node_id: str,
    plan_metadata: dict[int, PlanMetadata],
) -> MultiPlanRouteResultData:
    if from_node_id not in G_super or to_node_id not in G_super:
        return MultiPlanRouteResultData(
            status="no_path",
            message="Route endpoints are missing from the super graph",
            total_distance_meters=None,
            segments=[],
        )

    try:
        path = nx.astar_path(G_super, from_node_id, to_node_id, heuristic=lambda _a, _b: 0, weight="weight")
    except nx.NetworkXNoPath:
        return MultiPlanRouteResultData(
            status="no_path",
            message="No path between selected endpoints",
            total_distance_meters=None,
            segments=[],
        )

    segments: list[RouteSegmentData] = []
    total_distance = 0.0
    current_reconstruction_id: int | None = None
    current_coordinates: list[list[float]] = []

    for node_id in path:
        node_data = G_super.nodes[node_id]
        reconstruction_id = node_data.get("reconstruction_id")
        if isinstance(reconstruction_id, int) and current_reconstruction_id != reconstruction_id:
            if current_coordinates and current_reconstruction_id is not None:
                segments.append(RouteSegmentData(current_reconstruction_id, current_coordinates, None))
            current_reconstruction_id = reconstruction_id
            current_coordinates = []
        pos = node_data.get("pos")
        if pos is not None:
            current_coordinates.append([float(pos[0]), float(pos[1])])
    if current_coordinates and current_reconstruction_id is not None:
        segments.append(RouteSegmentData(current_reconstruction_id, current_coordinates, None))

    for source, target in zip(path, path[1:]):
        total_distance += float(G_super.edges[source, target].get("weight", 0.0))

    return MultiPlanRouteResultData(
        status="success",
        message=None,
        total_distance_meters=total_distance,
        segments=segments,
    )
