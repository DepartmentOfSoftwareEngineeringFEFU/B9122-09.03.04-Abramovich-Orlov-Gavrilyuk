"""Pure cross-floor routing & matching (multifloor-routing, subfeature D).

The algorithmic heart of D: project each floor's stair/elevator nodes into one
shared **building frame**, auto-match the shafts that line up vertically, merge
the per-floor nav graphs into one metric-weighted graph and run a metric A*
across it. Floor-keyed siblings of the legacy recon-keyed ``nav_graph.merge_floor_graphs``
/ ``find_multifloor_route_in_graph`` (which stay for the public recon path).

Layer rule (``prompts/architecture.md``): this module is PURE — it imports ONLY
``math`` / ``networkx`` / ``dataclasses`` / ``typing``. No ``cv2``, no DB, no HTTP,
no file IO. ``BuildingNavService`` loads the graphs + A's transforms and
feeds plain value objects in; it owns the 3D layout and all IO.

 for the exact
formulas: projection (with the ``k = nav_mask_w / floor_mask_w`` reconciliation),
 matching, merge in metres, metric A*.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

import networkx as nx
from networkx.utils import UnionFind


# Value objects (inputs / outputs of the pure functions)


@dataclass(frozen=True)
class FloorRouteEntry:
    """One floor's deserialised nav graph + the metadata the merge/route needs.

    Attributes:
        floor_id: ``Floor.id`` — the node-prefix + segment key.
        floor_number: building floor number (drives ordering + elevation).
        graph: deserialised ``floor_{id}_nav.json`` (nodes carry ``pos`` in
            canvas px, ``type``, and on room nodes the threaded transition
            metadata from).
        scale_factor: ``1/(ppm·k)`` from the nav metadata (canvas-px → metres).
        nav_mask_w / nav_mask_h: assembled-canvas dims from the nav metadata.
        floor_mask_w / floor_mask_h: ``Floor.mask_file`` dims (A's de-norm space).
        building_transform: A's similarity (floor-mask px → reference-mask px), or
            ``None`` (identity / reference floor).
        elevation_m: ``(number − min_number)·FLOOR_HEIGHT`` (the floor's height).
    """

    floor_id: int
    floor_number: int
    graph: nx.Graph
    scale_factor: float
    nav_mask_w: int
    nav_mask_h: int
    floor_mask_w: int
    floor_mask_h: int
    building_transform: Optional[dict]
    elevation_m: float


@dataclass(frozen=True)
class TransitionNode:
    """A stair/elevator room node projected into building-frame metres."""

    floor_id: int
    floor_number: int
    node_id: str  # the room node id within its floor graph, e.g. ``room_s1``
    room_type: str  # ``staircase`` | ``elevator``
    x_m: float
    y_m: float
    floor_from: Optional[int] = None
    floor_to: Optional[int] = None
    floors_excluded: list[int] = field(default_factory=list)
    connects_up: bool = True
    connects_down: bool = True


@dataclass(frozen=True)
class TransitionLink:
    """An accepted cross-floor link between two shaft nodes (lower → upper)."""

    lower_floor_id: int
    lower_node: str
    upper_floor_id: int
    upper_node: str
    type: str  # ``staircase`` | ``elevator``
    source: str  # ``auto`` | ``forced``
    distance_m: float


@dataclass(frozen=True)
class Unmatched:
    """A transition node the matcher could not pair (operator awareness)."""

    floor_id: int
    floor_number: int
    node: str
    type: str
    reason: str


# Project a node into the building frame


def project_to_building_frame(
    pos_canvas: tuple[float, float],
    k: float,
    building_transform: Optional[dict],
    ppm_ref: float,
) -> tuple[float, float]:
    """Project a node position into the shared metric building frame.

    Three steps: (1) canvas-px → floor-mask-px ``÷k`` (``k = nav_mask_w /
    floor_mask_w`` — the assembled canvas is ``master×k`` but ``building_transform``
    is over mask px); (2) apply A's similarity (floor-mask px → reference-mask
    px); (3) ref-px → metres ``÷ppm_ref``. ``building_transform=None`` ⇒ identity
    (the reference floor).

    Args:
        pos_canvas: node ``pos`` in canvas px.
        k: ``nav_mask_w / floor_mask_w`` (> 0).
        building_transform: ``{scale, rotation_rad, tx, ty}`` (ref-px units), or
            ``None`` for identity.
        ppm_ref: reference floor pixels-per-metre (> 0).

    Returns:
        ``(X_m, Y_m)`` — the node's XY in the metric building frame.

    Raises:
        ValueError: ``k <= 0`` or ``ppm_ref <= 0`` (cannot reconcile units).
    """
    if k <= 0:
        raise ValueError(f"invalid canvas factor k={k} (need k > 0)")
    if ppm_ref <= 0:
        raise ValueError(f"invalid ppm_ref={ppm_ref} (need ppm_ref > 0)")

    px = pos_canvas[0] / k
    py = pos_canvas[1] / k

    if building_transform is None:
        x_ref, y_ref = px, py
    else:
        scale = float(building_transform["scale"])
        rot = float(building_transform.get("rotation_rad", 0.0))
        tx = float(building_transform["tx"])
        ty = float(building_transform["ty"])
        c = scale * math.cos(rot)
        s = scale * math.sin(rot)
        x_ref = c * px - s * py + tx
        y_ref = s * px + c * py + ty

    return (x_ref / ppm_ref, y_ref / ppm_ref)


def _entry_k(entry: FloorRouteEntry) -> float:
    """Recover the floor's canvas factor ``k = nav_mask_w / floor_mask_w``."""
    if entry.floor_mask_w <= 0:
        return 0.0
    return entry.nav_mask_w / entry.floor_mask_w


def transition_nodes_from_entry(
    entry: FloorRouteEntry, ppm_ref: float
) -> list[TransitionNode]:
    """Extract + project a floor's stair/elevator room nodes.

    Pure helper the service calls per floor: filters room nodes of transition
    type, projects each ``pos`` into the building frame, and carries the threaded
    metadata. Raises ``ValueError`` if the floor's mask dims are missing
    (``k <= 0``) — the service maps that to 422.
    """
    k = _entry_k(entry)
    if k <= 0:
        raise ValueError(
            f"floor mask dims unavailable for floor {entry.floor_id}"
        )
    out: list[TransitionNode] = []
    for node_id, data in entry.graph.nodes(data=True):
        if data.get("type") != "room":
            continue
        rtype = data.get("room_type", "room")
        if rtype not in ("staircase", "elevator"):
            continue
        pos = data.get("pos")
        if pos is None:
            continue
        x_m, y_m = project_to_building_frame(
            (float(pos[0]), float(pos[1])), k, entry.building_transform, ppm_ref
        )
        out.append(
            TransitionNode(
                floor_id=entry.floor_id,
                floor_number=entry.floor_number,
                node_id=str(node_id),
                room_type=rtype,
                x_m=x_m,
                y_m=y_m,
                floor_from=data.get("floor_from"),
                floor_to=data.get("floor_to"),
                floors_excluded=list(data.get("floors_excluded") or []),
                connects_up=bool(data.get("connects_up", True)),
                connects_down=bool(data.get("connects_down", True)),
            )
        )
    return out


# Match cross-floor transitions


def _key(n: TransitionNode) -> tuple[int, str]:
    """Stable unique key for a transition node (floor + node id)."""
    return (n.floor_id, n.node_id)


def _nearest_on_floor(
    node: TransitionNode,
    candidates: list[TransitionNode],
    tolerance_m: float,
) -> Optional[TransitionNode]:
    """Nearest candidate within ``tolerance_m`` (deterministic tie-break)."""
    best: Optional[TransitionNode] = None
    best_d = math.inf
    for other in candidates:
        d = math.hypot(node.x_m - other.x_m, node.y_m - other.y_m)
        if d > tolerance_m:
            continue
        if best is None or d < best_d or (d == best_d and other.node_id < best.node_id):
            best = other
            best_d = d
    return best


def _cluster_by_shaft(
    nodes: list[TransitionNode], tolerance_m: float
) -> list[list[TransitionNode]]:
    """Group same-type nodes into shafts by MUTUAL-nearest across floors.

    Two nodes on different floors join the same shaft only when each is the
    other's nearest qualifying node on that other's floor — preventing two
    distinct nearby shafts from cross-merging (the ``mutual-nearest`` guard).
    """
    by_floor: dict[int, list[TransitionNode]] = {}
    for n in nodes:
        by_floor.setdefault(n.floor_number, []).append(n)
    floors = sorted(by_floor)

    uf: UnionFind = UnionFind()
    for n in nodes:
        _ = uf[_key(n)]  # ensure every node is a singleton at minimum

    for a in nodes:
        for f in floors:
            if f == a.floor_number:
                continue
            b = _nearest_on_floor(a, by_floor[f], tolerance_m)
            if b is None:
                continue
            a_back = _nearest_on_floor(b, by_floor[a.floor_number], tolerance_m)
            if a_back is not None and _key(a_back) == _key(a):
                uf.union(_key(a), _key(b))

    groups: dict[object, list[TransitionNode]] = {}
    for n in nodes:
        groups.setdefault(uf[_key(n)], []).append(n)
    return list(groups.values())


def _stair_links(
    ordered: list[TransitionNode],
) -> list[tuple[TransitionNode, TransitionNode]]:
    """Link consecutive ADJACENT-floor stairs, gated by up/down."""
    pairs: list[tuple[TransitionNode, TransitionNode]] = []
    for i in range(len(ordered) - 1):
        lo = ordered[i]
        hi = ordered[i + 1]
        if hi.floor_number - lo.floor_number != 1:
            continue  # a staircase never skips a floor
        if lo.connects_up and hi.connects_down:
            pairs.append((lo, hi))
    return pairs


def _elevator_stop_valid(n: TransitionNode) -> bool:
    """True iff the node's own floor is a served stop (range minus excluded)."""
    if n.floor_from is None or n.floor_to is None:
        return True  # no range constraint → always a valid stop
    if not (n.floor_from <= n.floor_number <= n.floor_to):
        return False
    return n.floor_number not in (n.floors_excluded or [])


def _elevator_links(
    ordered: list[TransitionNode],
) -> list[tuple[TransitionNode, TransitionNode]]:
    """Link consecutive VALID elevator stops (skips excluded/missing)."""
    valid = [n for n in ordered if _elevator_stop_valid(n)]
    return [(valid[i], valid[i + 1]) for i in range(len(valid) - 1)]


def match_cross_floor_transitions(
    transition_nodes: list[TransitionNode],
    tolerance_m: float,
) -> tuple[list[TransitionLink], list[Unmatched]]:
    """Auto-match stair/elevator shafts in the building frame.

    Clusters same-type nodes into shafts (mutual-nearest within ``tolerance_m``),
    then links consecutive members per type: stairs only across ADJACENT floors
    gated by ``connects_up``/``connects_down``; elevators across consecutive valid
    stops (range minus excluded). Stairs and elevators never cross-match.

    Returns:
        ``(links, unmatched)`` — accepted auto links (``source="auto"``) and the
        nodes left without any link.
    """
    links: list[TransitionLink] = []
    matched: set[tuple[int, str]] = set()

    for rtype in ("staircase", "elevator"):
        same_type = [n for n in transition_nodes if n.room_type == rtype]
        if not same_type:
            continue
        for cluster in _cluster_by_shaft(same_type, tolerance_m):
            ordered = sorted(cluster, key=lambda n: n.floor_number)
            pairs = (
                _stair_links(ordered)
                if rtype == "staircase"
                else _elevator_links(ordered)
            )
            for lo, hi in pairs:
                d = math.hypot(lo.x_m - hi.x_m, lo.y_m - hi.y_m)
                links.append(
                    TransitionLink(
                        lower_floor_id=lo.floor_id,
                        lower_node=lo.node_id,
                        upper_floor_id=hi.floor_id,
                        upper_node=hi.node_id,
                        type=rtype,
                        source="auto",
                        distance_m=round(d, 4),
                    )
                )
                matched.add(_key(lo))
                matched.add(_key(hi))

    unmatched = [
        Unmatched(
            floor_id=n.floor_id,
            floor_number=n.floor_number,
            node=n.node_id,
            type=n.room_type,
            reason="no_partner_within_tolerance",
        )
        for n in transition_nodes
        if _key(n) not in matched
    ]
    return links, unmatched


# Merge floor graphs (Floor-keyed, metric-weighted)


def merge_floor_graphs_by_id(
    floor_entries: list[FloorRouteEntry],
    links: list[TransitionLink],
    transition_cost_m: float,
    ppm_ref: float,
) -> nx.Graph:
    """Merge per-floor graphs into one metric graph + transition edges.

    Prefixes every node ``"{floor_id}:{node}"`` and carries ``floor_id`` /
    ``floor_number`` / ``elevation_m`` / ``building_xy_m`` for the A*
    heuristic + 3D layout. Intra-floor edge weights are converted to metres
    (``× scale_factor``); ``pts`` are preserved for polyline reconstruction. Each
    accepted ``link`` becomes a ``floor_transition`` edge weighted
    ``transition_cost_m``. The service passes the FINAL link set (disable already
    removed, force already added) — this function only wires it.
    """
    merged = nx.Graph()
    for entry in floor_entries:
        prefix = f"{entry.floor_id}:"
        k = _entry_k(entry)
        for node_id, data in entry.graph.nodes(data=True):
            pos = data.get("pos")
            xy: Optional[tuple[float, float]] = None
            if pos is not None and k > 0 and ppm_ref > 0:
                try:
                    xy = project_to_building_frame(
                        (float(pos[0]), float(pos[1])),
                        k,
                        entry.building_transform,
                        ppm_ref,
                    )
                except (ValueError, TypeError):
                    xy = None
            merged.add_node(
                f"{prefix}{node_id}",
                floor_id=entry.floor_id,
                floor_number=entry.floor_number,
                elevation_m=entry.elevation_m,
                building_xy_m=xy,
                **data,
            )
        for u, v, edge_data in entry.graph.edges(data=True):
            attrs = dict(edge_data)
            attrs["weight"] = float(edge_data.get("weight", 0.0)) * entry.scale_factor
            merged.add_edge(f"{prefix}{u}", f"{prefix}{v}", **attrs)

    for link in links:
        lo = f"{link.lower_floor_id}:{link.lower_node}"
        hi = f"{link.upper_floor_id}:{link.upper_node}"
        if merged.has_node(lo) and merged.has_node(hi):
            merged.add_edge(
                lo,
                hi,
                weight=float(transition_cost_m),
                type="floor_transition",
                transition_type=link.type,
            )
    return merged


# Find the route (metric A*)


def _route_heuristic(merged: nx.Graph):
    """Admissible 3D straight-line heuristic over ``building_xy_m`` + elevation."""

    def h(u: str, v: str) -> float:
        du = merged.nodes[u]
        dv = merged.nodes[v]
        xu = du.get("building_xy_m")
        xv = dv.get("building_xy_m")
        if xu is None or xv is None:
            return 0.0  # fall back to Dijkstra for un-projected nodes
        zu = du.get("elevation_m", 0.0) or 0.0
        zv = dv.get("elevation_m", 0.0) or 0.0
        return math.hypot(xv[0] - xu[0], xv[1] - xu[1], zv - zu)

    return h


def _orient(start: tuple[float, float], pts: list) -> list:
    """Orient an edge's ``pts`` so they run away from ``start``."""
    first, last = pts[0], pts[-1]
    d0 = math.hypot(start[0] - first[0], start[1] - first[1])
    d1 = math.hypot(start[0] - last[0], start[1] - last[1])
    return list(pts) if d0 <= d1 else list(reversed(pts))


def _dedupe(coords: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Drop consecutive duplicate points."""
    out: list[tuple[float, float]] = []
    for p in coords:
        if not out or out[-1] != p:
            out.append(p)
    return out


def _node_id(floor_id: int, room: str) -> str:
    """Build a prefixed node id, accepting bare or ``room_``-prefixed input."""
    bare = room if room.startswith("room_") else f"room_{room}"
    return f"{floor_id}:{bare}"


def find_multifloor_route_by_id(
    merged: nx.Graph,
    from_floor_id: int,
    from_room: str,
    to_floor_id: int,
    to_room: str,
) -> dict:
    """Metric A* across the merged graph, segmented by floor.

    Returns a dict with ``status`` (``success`` | ``no_path``), ``path_segments``
    (``floor_id`` / ``floor_number`` / ``coords_2d`` canvas-px per floor),
    ``transitions_used`` (each stair/lift hop with canvas-px endpoints) and
    ``total_distance_m`` (Σ metric edge weights).

    Raises:
        ValueError: an endpoint room id is absent in its floor graph (→ 422).
    """
    from_node = _node_id(from_floor_id, from_room)
    to_node = _node_id(to_floor_id, to_room)
    if from_node not in merged:
        raise ValueError(f"Комната '{from_room}' не найдена в графе")
    if to_node not in merged:
        raise ValueError(f"Комната '{to_room}' не найдена в графе")

    if not nx.has_path(merged, from_node, to_node):
        return {
            "status": "no_path",
            "path_segments": [],
            "transitions_used": [],
            "total_distance_m": 0.0,
        }

    path_nodes = nx.astar_path(
        merged, from_node, to_node,
        heuristic=_route_heuristic(merged), weight="weight",
    )

    total_m = 0.0
    for i in range(len(path_nodes) - 1):
        edge = merged.get_edge_data(path_nodes[i], path_nodes[i + 1]) or {}
        total_m += float(edge.get("weight", 0.0))

    segments: list[dict] = []
    transitions: list[dict] = []
    cur_fid: Optional[int] = None
    cur_fnum: Optional[int] = None
    cur: list[tuple[float, float]] = []

    def flush() -> None:
        if cur:
            segments.append(
                {
                    "floor_id": cur_fid,
                    "floor_number": cur_fnum,
                    "coords_2d": _dedupe(cur),
                }
            )

    for i, node in enumerate(path_nodes):
        nd = merged.nodes[node]
        fid = nd.get("floor_id")
        if fid != cur_fid:
            flush()
            cur = []
            cur_fid = fid
            cur_fnum = nd.get("floor_number")
        pos = nd.get("pos")
        if pos is not None:
            cur.append((float(pos[0]), float(pos[1])))
        if i < len(path_nodes) - 1:
            nxt = path_nodes[i + 1]
            edge = merged.get_edge_data(node, nxt) or {}
            if edge.get("type") == "floor_transition":
                npos = merged.nodes[nxt].get("pos")
                transitions.append(
                    {
                        "type": edge.get("transition_type", ""),
                        "from_floor_id": fid,
                        # Bare node id (drop the "{floor_id}:" merge prefix) so the
                        # client can match the hop to a stair/lift room icon.
                        "from_node": node.split(":", 1)[-1],
                        "from_pos": (
                            (float(pos[0]), float(pos[1])) if pos is not None else None
                        ),
                        "to_floor_id": merged.nodes[nxt].get("floor_id"),
                        "to_node": nxt.split(":", 1)[-1],
                        "to_pos": (
                            (float(npos[0]), float(npos[1])) if npos is not None else None
                        ),
                    }
                )
            else:
                pts = edge.get("pts")
                if pts and len(pts) > 1 and pos is not None:
                    oriented = _orient((float(pos[0]), float(pos[1])), pts)
                    cur.extend((float(p[0]), float(p[1])) for p in oriented[1:])
    flush()

    return {
        "status": "success",
        "path_segments": segments,
        "transitions_used": transitions,
        "total_distance_m": total_m,
    }
