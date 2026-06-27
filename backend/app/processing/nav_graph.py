import logging
import math
import time

import cv2
import networkx as nx
import numpy as np
from networkx.readwrite import json_graph
from shapely.geometry import LineString, Point
from skimage.morphology import binary_closing, skeletonize, square

from app.core.exceptions import ImageProcessingError

logger = logging.getLogger(__name__)

_MIN_CORRIDOR_PX: float = 3.0
_MAX_DILATE_PX: int = 30


def extract_corridor_mask(
    wall_mask: np.ndarray,
    rooms: list[dict],
    mask_width: int,
    mask_height: int,
    wall_thickness_px: float,
    corridor_ratio: float = 1.5,
) -> np.ndarray:
    """
    Извлекает маску коридоров через distance transform.

    Пиксели свободного пространства, у которых расстояние до ближайшей стены
    >= corridor_threshold, считаются «широкими проходами» (коридорами).
    Самый большой внутренний компонент расширяется обратно до исходных границ.

    Args:
        wall_mask: бинарная маска стен (uint8, стены=255, фон=0)
        rooms: список комнат с полями x, y, width, height, room_type (нормализованные [0,1])
        mask_width: ширина маски в пикселях
        mask_height: высота маски в пикселях
        wall_thickness_px: толщина стен в пикселях (из compute_wall_thickness)
        corridor_ratio: множитель толщины стены для порога коридора

    Returns:
        Бинарная маска коридоров (uint8, коридор=255, остальное=0)
    """
    t0 = time.perf_counter()

    # 1. Валидация входных данных
    if wall_mask is None or wall_mask.size == 0:
        raise ImageProcessingError("extract_corridor_mask", "Empty mask")
    if wall_mask.dtype != np.uint8:
        raise ImageProcessingError(
            "extract_corridor_mask",
            f"Expected uint8, got {wall_mask.dtype}",
        )

    # 2. Свободное пространство
    free_space = cv2.bitwise_not(wall_mask)

    # 3. Distance transform — расстояние каждого пикселя до ближайшей стены
    dist = cv2.distanceTransform(free_space, cv2.DIST_L2, 5)

    # 4. Порог коридора
    if wall_thickness_px <= 0:
        logger.warning(
            "extract_corridor_mask: wall_thickness_px <= 0, using MIN_CORRIDOR_PX fallback"
        )
        corridor_threshold = _MIN_CORRIDOR_PX
    else:
        corridor_threshold = max(_MIN_CORRIDOR_PX, corridor_ratio * wall_thickness_px)

    # 5. Маска «широких проходов»
    wide_passage = (dist >= corridor_threshold).astype(np.uint8) * 255

    # 6. Проверка наличия широких проходов
    if np.sum(wide_passage > 0) == 0:
        logger.warning("extract_corridor_mask: no wide passages found")
        return np.zeros_like(wall_mask)

    # 7. Связные компоненты широких проходов
    h_mask, w_mask = wall_mask.shape[:2]
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(
        wide_passage, connectivity=8
    )

    # Компоненты, касающиеся границ изображения (= экстерьер)
    border_labels: set[int] = set()
    border_labels.update(int(v) for v in labels[0, :].flat)
    border_labels.update(int(v) for v in labels[h_mask - 1, :].flat)
    border_labels.update(int(v) for v in labels[:, 0].flat)
    border_labels.update(int(v) for v in labels[:, w_mask - 1].flat)
    border_labels.discard(0)

    # Экстерьер = самый большой компонент, КАСАЮЩИЙСЯ границы изображения (плюс
    # любой граничный компонент крупнее max_corridor_area — слипшийся/протёкший
    # блоб). ВНУТРЕННИЕ (не-граничные) компоненты сохраняются при ЛЮБОМ размере:
    # одна секция может законно занимать >50% канвы. R1: сохраняем КАЖДЫЙ
    # внутренний компонент (а не только самый большой) → у каждой физически
    # отдельной секции появляется свой скелет.
    max_corridor_area = h_mask * w_mask * 0.5

    exterior_label = -1
    exterior_area = 0
    for label_id in border_labels:
        area = int(stats[label_id, cv2.CC_STAT_AREA])
        if area > exterior_area:
            exterior_area = area
            exterior_label = label_id

    exterior_labels: set[int] = set()
    if exterior_label != -1:
        exterior_labels.add(exterior_label)
    for label_id in border_labels:
        if int(stats[label_id, cv2.CC_STAT_AREA]) > max_corridor_area:
            exterior_labels.add(label_id)

    # Порог шума — мелкие пятна отбрасываем.
    min_corridor_area_px = max(1.0, corridor_threshold ** 2)

    # 8. Грубая маска коридора — объединение ВСЕХ внутренних (не-граничных)
    # компонентов выше порога шума.
    corridor_rough = np.zeros_like(wall_mask)
    kept_components = 0
    for label_id in range(1, num_labels):
        if label_id in border_labels:
            continue
        if int(stats[label_id, cv2.CC_STAT_AREA]) < min_corridor_area_px:
            continue
        corridor_rough[labels == label_id] = 255
        kept_components += 1

    # Фоллбэк: внутренних компонентов нет (всё касается границы) — сохраняем ВСЕ
    # не-экстерьерные граничные компоненты (а не только самый большой, как было).
    if kept_components == 0:
        logger.warning(
            "extract_corridor_mask: no interior components, using non-exterior border components"
        )
        for label_id in border_labels:
            if label_id in exterior_labels:
                continue
            if int(stats[label_id, cv2.CC_STAT_AREA]) < min_corridor_area_px:
                continue
            corridor_rough[labels == label_id] = 255
            kept_components += 1

    # Последний resort: одна секция, целиком на границе (нет L/R стен) — берём
    # сам экстерьер, иначе одно-секционные планы остались бы без коридора.
    if kept_components == 0 and exterior_label != -1:
        corridor_rough[labels == exterior_label] = 255
        kept_components += 1

    if kept_components == 0:
        logger.warning("extract_corridor_mask: no free space found")
        return np.zeros_like(wall_mask)

    # 9. Расширяем обратно → пересекаем с оригиналом → точные границы
    dilate_px = max(1, min(int(wall_thickness_px) if wall_thickness_px > 0 else 1, _MAX_DILATE_PX))
    dilate_kernel = np.ones((dilate_px, dilate_px), np.uint8)
    corridor_expanded = cv2.dilate(corridor_rough, dilate_kernel)
    corridor_mask = cv2.bitwise_and(free_space, corridor_expanded)

    # 10. Вычитаем размеченные комнаты
    room_types_to_subtract = {'room', 'staircase', 'elevator'}
    manual_subtracted = 0
    for room in rooms:
        if room.get('room_type', 'room') in room_types_to_subtract:
            x = int(room['x'] * mask_width)
            y = int(room['y'] * mask_height)
            w = int(room['width'] * mask_width)
            h = int(room['height'] * mask_height)
            cv2.rectangle(corridor_mask, (x, y), (x + w, y + h), 0, -1)
            manual_subtracted += 1

    # 11. Логирование
    logger.info(
        "extract_corridor_mask: %dx%d, threshold=%.1f (ratio=%.1f * %.1fpx), "
        "components=%d, kept=%d, manual_sub=%d, %.1fms",
        mask_width, mask_height,
        corridor_threshold, corridor_ratio, wall_thickness_px,
        num_labels - 1,
        kept_components,
        manual_subtracted,
        (time.perf_counter() - t0) * 1000,
    )

    return corridor_mask


def build_skeleton(corridor_mask: np.ndarray) -> np.ndarray:
    """
    Применяет морфологическое закрытие и скелетонизацию к маске коридоров.
    """
    t0 = time.perf_counter()

    binary = corridor_mask > 0
    cleaned = binary_closing(binary, square(5))
    skeleton = skeletonize(cleaned)
    result = skeleton.astype(np.uint8) * 255

    logger.info("build_skeleton: %.1fms", (time.perf_counter() - t0) * 1000)
    return result


def build_topology_graph(skeleton: np.ndarray) -> nx.Graph:
    """
    Строит топологический граф из пиксельного скелета через sknw.
    """
    import sknw

    t0 = time.perf_counter()

    skel_input = (skeleton > 0).astype(np.uint16)
    graph_sk = sknw.build_sknw(skel_input, multi=False, iso=False)

    G = nx.Graph()

    for node_id in graph_sk.nodes():
        cy, cx = graph_sk.nodes[node_id]['o']
        G.add_node(
            int(node_id),
            type='corridor_node',
            pos=(float(cx), float(cy)),
        )

    for u, v, edge_data in graph_sk.edges(data=True):
        weight = float(edge_data.get('weight', 0))
        pts = [(float(pt[1]), float(pt[0])) for pt in edge_data.get('pts', [])]
        G.add_edge(
            int(u), int(v),
            weight=weight,
            pts=pts,
            type='corridor_edge',
        )

    logger.info(
        "build_topology_graph: %d nodes, %d edges, %.1fms",
        G.number_of_nodes(), G.number_of_edges(),
        (time.perf_counter() - t0) * 1000,
    )
    return G


def prune_dendrites(G: nx.Graph, min_branch_length: float = 20.0) -> nx.Graph:
    """
    Удаляет короткие тупиковые ответвления скелета (дендриты).
    """
    t0 = time.perf_counter()
    removed_total = 0

    changed = True
    while changed:
        changed = False
        dead_ends = [n for n, deg in dict(G.degree()).items() if deg == 1]

        for node in dead_ends:
            if node not in G:
                continue
            neighbors = list(G.neighbors(node))
            if not neighbors:
                continue
            neighbor = neighbors[0]
            edge_data = G.get_edge_data(node, neighbor)
            if edge_data and edge_data.get('weight', float('inf')) < min_branch_length:
                G.remove_node(node)
                changed = True
                removed_total += 1

    logger.info(
        "prune_dendrites: removed %d dead ends, %.1fms",
        removed_total, (time.perf_counter() - t0) * 1000,
    )
    return G


def integrate_semantics(
    G: nx.Graph,
    rooms: list[dict],
    doors: list[dict],
    mask_width: int,
    mask_height: int,
    wall_mask: np.ndarray | None = None,
    max_snap_dist_px: float = float("inf"),
    skip_px: float = 0.0,
) -> nx.Graph:
    """
    Интегрирует семантические объекты (комнаты, двери) в топологический граф коридоров.

    R5 — ограниченный snap двери к коридору. Кандидат на привязку принимается,
    только если он (а) ближе ``max_snap_dist_px`` и (б) виден из двери по прямой
    (seeded line-of-sight через ``_los_clear``). Если ни один кандидат не проходит
    оба условия, дверь остаётся узлом без ребра к коридору (честный «нет пути»
    вместо привязки через стену к чужой секции).

    Args:
        wall_mask: ассемблированная маска этажа (uint8, стены=255) для LOS-проверки.
            ``None`` (по умолчанию) отключает оба ограничения → прежнее
            безусловное поведение (используется одиночным ``nav_service``).
        max_snap_dist_px: максимальная дистанция дверь→коридор. ``inf`` = без
            ограничения (прежнее поведение).
        skip_px: на сколько пикселей «отступить» от двери вдоль луча перед
            LOS-проверкой, чтобы собственная стена дверного проёма не считалась
            препятствием (см. ``_los_clear``).
    """
    t0 = time.perf_counter()

    # --- 1. Узлы комнат ---
    room_nodes: dict[str, str] = {}
    for room in rooms:
        rx = room['x'] * mask_width
        ry = room['y'] * mask_height
        rw = room['width'] * mask_width
        rh = room['height'] * mask_height
        cx = rx + rw / 2.0
        cy = ry + rh / 2.0

        node_id = f"room_{room['id']}"
        node_attrs = {
            'type': 'room',
            'pos': (cx, cy),
            'room_id': room['id'],
            'room_name': room.get('name', ''),
            'room_type': room.get('room_type', 'room'),
            'bbox': (rx, ry, rw, rh),
            # Transition metadata (multifloor-routing, D) — copied onto the node
            # so route-time matching reads it straight off the persisted graph.
            # Default-safe: legacy callers (single-plan nav_service) omit these
            # keys → stairs open both ways, no elevator range constraint.
            'floor_from': room.get('floor_from'),
            'floor_to': room.get('floor_to'),
            'floors_excluded': room.get('floors_excluded', []),
            'connects_up': room.get('connects_up', True),
            'connects_down': room.get('connects_down', True),
        }
        # Oriented box from the floor transform (rotation-aware 3D room box, Q2
        # fix). Absent for the single-plan caller → node keeps only the AABB bbox.
        if 'obb_w' in room:
            node_attrs['obox'] = (
                room['obb_cx'] * mask_width,
                room['obb_cy'] * mask_height,
                room['obb_w'] * mask_width,
                room['obb_h'] * mask_height,
                room.get('rotation_rad', 0.0),
            )
        G.add_node(node_id, **node_attrs)
        room_nodes[room['id']] = node_id

    # --- 2. Геометрия коридоров для snap ---
    edges_geometry = []
    for u, v, data in list(G.edges(data=True)):
        if data.get('type') == 'corridor_edge' and data.get('pts'):
            pts = data['pts']
            if len(pts) >= 2:
                line = LineString(pts)
                edges_geometry.append((u, v, line, data))

    # --- 3. Обработка дверей ---
    for door in doors:
        dx1 = door['x1'] * mask_width
        dy1 = door['y1'] * mask_height
        dx2 = door['x2'] * mask_width
        dy2 = door['y2'] * mask_height
        dmx = (dx1 + dx2) / 2.0
        dmy = (dy1 + dy2) / 2.0

        door_node_id = f"door_{door['id']}"
        G.add_node(door_node_id, type='door', pos=(dmx, dmy), door_id=door['id'])

        # --- 3a. Связь дверь→комната ---
        linked_room_node = None
        if door.get('room_id') and door['room_id'] in room_nodes:
            linked_room_node = room_nodes[door['room_id']]
        else:
            min_dist = float('inf')
            for r_id, r_node in room_nodes.items():
                rx, ry = G.nodes[r_node]['pos']
                dist = math.hypot(rx - dmx, ry - dmy)
                if dist < min_dist:
                    min_dist = dist
                    linked_room_node = r_node

        if linked_room_node:
            room_pos = G.nodes[linked_room_node]['pos']
            dist_room_door = math.hypot(room_pos[0] - dmx, room_pos[1] - dmy)
            G.add_edge(linked_room_node, door_node_id, weight=dist_room_door, type='room_to_door')

        # --- 3b. Snap дверь → скелет коридора ---
        if not edges_geometry:
            continue

        door_pt = Point(dmx, dmy)
        best_dist = float('inf')
        best_snap = None
        best_edge = None

        for u, v, geom_line, edge_data in edges_geometry:
            proj_dist = geom_line.project(door_pt)
            snap_pt = geom_line.interpolate(proj_dist)
            dist_to_corridor = door_pt.distance(snap_pt)

            # R5 (а): слишком далеко — это снимает «прыжки» через открытый зазор.
            if dist_to_corridor > max_snap_dist_px:
                continue
            # R5 (б): между дверью и коридором стена — отбрасываем (защита от
            # привязки к скелету ЧУЖОЙ секции). Луч засевается за собственной
            # стеной дверного проёма (см. _los_clear, 🔴-1).
            if wall_mask is not None and not _los_clear(
                (dmx, dmy), (snap_pt.x, snap_pt.y), wall_mask, skip_px
            ):
                continue

            if dist_to_corridor < best_dist:
                best_dist = dist_to_corridor
                best_snap = snap_pt
                best_edge = (u, v, geom_line, edge_data)

        if best_snap is None or best_edge is None:
            continue

        u, v, geom_line, edge_data = best_edge
        entry_node_id = f"entry_{door['id']}"
        ex, ey = best_snap.x, best_snap.y

        G.add_node(entry_node_id, type='corridor_entry', pos=(ex, ey))
        G.add_edge(door_node_id, entry_node_id, weight=best_dist, type='door_to_corridor')

        # --- 3c. Расщепление ребра коридора ---
        u_pos = np.array(G.nodes[u]['pos'])
        v_pos = np.array(G.nodes[v]['pos'])
        entry_pos = np.array([ex, ey])

        dist_u_entry = float(np.linalg.norm(u_pos - entry_pos))
        dist_v_entry = float(np.linalg.norm(v_pos - entry_pos))

        proj_normalized = geom_line.project(best_snap, normalized=True)
        total_pts = edge_data.get('pts', [])
        split_idx = max(1, int(len(total_pts) * proj_normalized))
        pts_u_to_entry = total_pts[:split_idx] + [(ex, ey)]
        pts_entry_to_v = [(ex, ey)] + total_pts[split_idx:]

        if G.has_edge(u, v):
            G.remove_edge(u, v)

        G.add_edge(u, entry_node_id, weight=dist_u_entry, type='corridor_edge', pts=pts_u_to_entry)
        G.add_edge(entry_node_id, v, weight=dist_v_entry, type='corridor_edge', pts=pts_entry_to_v)

    logger.info(
        "integrate_semantics: +%d rooms, +%d doors, %.1fms",
        len(rooms), len(doors), (time.perf_counter() - t0) * 1000,
    )
    return G


def serialize_nav_graph(
    G: nx.Graph,
    mask_width: int,
    mask_height: int,
    scale_factor: float,
) -> dict:
    """Сериализует граф в JSON-совместимый словарь."""
    graph_data = json_graph.node_link_data(G)

    return {
        "version": 1,
        "metadata": {
            "mask_width": mask_width,
            "mask_height": mask_height,
            "scale_factor": scale_factor,
            "nodes_count": G.number_of_nodes(),
            "edges_count": G.number_of_edges(),
            "room_nodes": [n for n, d in G.nodes(data=True) if d.get('type') == 'room'],
            "door_nodes": [n for n, d in G.nodes(data=True) if d.get('type') == 'door'],
        },
        "graph": graph_data,
    }


def deserialize_nav_graph(data: dict) -> tuple[nx.Graph, dict]:
    """Восстанавливает граф из JSON. Returns: (nx.Graph, metadata_dict)"""
    G = json_graph.node_link_graph(data["graph"])
    return G, data["metadata"]


def find_route(
    G: nx.Graph,
    from_room_id: str,
    to_room_id: str,
) -> dict | None:
    """
    Поиск кратчайшего пути A* между двумя комнатами.

    Returns dict с полями path_nodes, path_coords_2d, total_distance_px
    или None если путь не найден.
    """
    t0 = time.perf_counter()

    from_node = from_room_id if from_room_id.startswith("room_") else f"room_{from_room_id}"
    to_node = to_room_id if to_room_id.startswith("room_") else f"room_{to_room_id}"

    if from_node not in G.nodes():
        logger.warning("find_route: source node %s not in graph", from_node)
        return None
    if to_node not in G.nodes():
        logger.warning("find_route: target node %s not in graph", to_node)
        return None

    if not nx.has_path(G, from_node, to_node):
        # Диагностика: разбираем компоненты связности, чтобы понять,
        # почему путь не найден (фрагментированный коридор vs синглтон-комната).
        components = list(nx.connected_components(G))
        node_comp_idx: dict = {}
        for idx, comp in enumerate(components):
            for n in comp:
                node_comp_idx[n] = idx

        def _summarize(node_id: str) -> str:
            idx = node_comp_idx.get(node_id)
            if idx is None:
                return f"{node_id}: NOT IN ANY COMPONENT"
            comp = components[idx]
            type_counts: dict[str, int] = {}
            for n in comp:
                t = G.nodes[n].get('type', 'unknown')
                type_counts[t] = type_counts.get(t, 0) + 1
            pos = G.nodes[node_id].get('pos')
            return (
                f"{node_id} in component #{idx} (size={len(comp)}, "
                f"types={type_counts}, node_pos={pos})"
            )

        largest_idx = max(range(len(components)), key=lambda i: len(components[i]))
        singletons = sum(1 for c in components if len(c) == 1)

        logger.warning(
            "find_route: no path from %s to %s | total_components=%d, "
            "largest_component_size=%d, singletons=%d | FROM: %s | TO: %s",
            from_node, to_node,
            len(components),
            len(components[largest_idx]),
            singletons,
            _summarize(from_node),
            _summarize(to_node),
        )
        return None

    def heuristic(u, v):
        u_pos = G.nodes[u].get('pos', (0, 0))
        v_pos = G.nodes[v].get('pos', (0, 0))
        return math.hypot(u_pos[0] - v_pos[0], u_pos[1] - v_pos[1])

    try:
        path_nodes = nx.astar_path(G, from_node, to_node, heuristic=heuristic, weight='weight')
    except nx.NetworkXNoPath:
        return None

    path_coords_2d = []
    total_distance = 0.0

    for i in range(len(path_nodes)):
        node = path_nodes[i]
        node_pos = G.nodes[node].get('pos', (0, 0))

        if i < len(path_nodes) - 1:
            next_node = path_nodes[i + 1]
            edge_data = G.get_edge_data(node, next_node)

            if edge_data:
                total_distance += edge_data.get('weight', 0)
                pts = edge_data.get('pts', [])

                if pts and len(pts) > 1:
                    first_pt = pts[0]
                    last_pt = pts[-1]
                    dist_to_first = math.hypot(node_pos[0] - first_pt[0], node_pos[1] - first_pt[1])
                    dist_to_last = math.hypot(node_pos[0] - last_pt[0], node_pos[1] - last_pt[1])

                    if dist_to_first <= dist_to_last:
                        path_coords_2d.extend(pts)
                    else:
                        path_coords_2d.extend(reversed(pts))
                else:
                    path_coords_2d.append(node_pos)
            else:
                path_coords_2d.append(node_pos)
        else:
            path_coords_2d.append(node_pos)

    deduped = [path_coords_2d[0]] if path_coords_2d else []
    for pt in path_coords_2d[1:]:
        if pt != deduped[-1]:
            deduped.append(pt)

    simplified = simplify_path(
        deduped, dp_epsilon=3.0, angle_threshold_deg=5.0, min_point_distance=5.0,
    )

    logger.info(
        "find_route: %s → %s, %d nodes, %d coords, %.0fpx, %.1fms",
        from_node, to_node, len(path_nodes), len(simplified),
        total_distance, (time.perf_counter() - t0) * 1000,
    )

    return {
        "path_nodes": path_nodes,
        "path_coords_2d": simplified,
        "total_distance_px": total_distance,
    }


def los_prune(coords_2d: list, wall_mask: np.ndarray) -> list:
    """
    Удаляет промежуточные точки, если между start и end
    можно провести прямую без пересечения стен.
    """
    if len(coords_2d) < 3:
        return coords_2d

    result = [coords_2d[0]]
    i = 0

    while i < len(coords_2d) - 1:
        best_j = i + 1
        for j in range(len(coords_2d) - 1, i + 1, -1):
            if _line_of_sight(coords_2d[i], coords_2d[j], wall_mask):
                best_j = j
                break
        result.append(coords_2d[best_j])
        i = best_j

    return result


def bridge_graph_components(
    G: nx.Graph,
    wall_mask: np.ndarray,
    max_bridge_dist_px: float,
) -> nx.Graph:
    """Сшивает разные компоненты связности короткими wall-clear рёбрами-мостами.

    Скелетизация коридоров часто рвёт единый коридор на изолированные фрагменты
    (разрыв в 1 пиксель медиальной оси). A* по такому графу не находит маршрут
    между фрагментами. По образцу Краскала добавляется минимальный набор коротких
    рёбер-мостов: для каждой пары узлов из РАЗНЫХ компонент, отстоящих не дальше
    ``max_bridge_dist_px`` и соединимых прямой БЕЗ пересечения стены
    (``_line_of_sight``), мост добавляется в порядке возрастания длины, пока
    компоненты сливаются. LOS-гейт — настоящий предохранитель: он отказывается
    сшивать фрагменты по разные стороны стены.

    Чистая функция: только ``math`` / ``networkx`` + ``_line_of_sight`` этого
    модуля. Мутирует и возвращает ``G`` (как ``prune_dendrites`` /
    ``integrate_semantics``).

    Args:
        G: граф; у узлов-коридоров атрибут ``pos = (x_px, y_px)``.
        wall_mask: ``(H, W)`` uint8 ``{0,255}`` — белый (> 127) = стена.
        max_bridge_dist_px: максимальная длина моста в пикселях.

    Returns:
        тот же ``G`` с добавленными рёбрами-мостами
        (``type='corridor_edge'``, ``bridge=True``).
    """
    t0 = time.perf_counter()
    nodes = [(n, data["pos"]) for n, data in G.nodes(data=True) if "pos" in data]

    # Засеять текущие компоненты. Изолированные узлы (без рёбер) создаются лениво
    # как свои синглтоны при первом обращении uf[node] — это и есть их компонента.
    uf = nx.utils.UnionFind()
    for u, v in G.edges():
        uf.union(u, v)

    candidates: list[tuple[float, int, int]] = []
    for i in range(len(nodes)):
        a, pos_a = nodes[i]
        for j in range(i + 1, len(nodes)):
            b, pos_b = nodes[j]
            dist = math.hypot(pos_a[0] - pos_b[0], pos_a[1] - pos_b[1])
            if dist > max_bridge_dist_px:
                continue
            if uf[a] == uf[b]:
                continue
            if not _line_of_sight(pos_a, pos_b, wall_mask):
                continue
            candidates.append((dist, i, j))

    candidates.sort(key=lambda c: c[0])

    bridges_added = 0
    for dist, i, j in candidates:
        a, pos_a = nodes[i]
        b, pos_b = nodes[j]
        if uf[a] == uf[b]:           # уже слиты предыдущим мостом
            continue
        G.add_edge(
            a, b, weight=dist, type="corridor_edge",
            pts=[pos_a, pos_b], bridge=True,
        )
        uf.union(a, b)
        bridges_added += 1

    logger.info(
        "bridge_graph_components: +%d bridges, %d candidates, %.1fms",
        bridges_added, len(candidates), (time.perf_counter() - t0) * 1000,
    )
    return G


def _line_of_sight(p1: tuple, p2: tuple, wall_mask: np.ndarray) -> bool:
    """Проверяет, что прямая p1→p2 не пересекает стены (белые пиксели)."""
    x1, y1 = int(p1[0]), int(p1[1])
    x2, y2 = int(p2[0]), int(p2[1])

    dx = abs(x2 - x1)
    dy = abs(y2 - y1)
    sx = 1 if x1 < x2 else -1
    sy = 1 if y1 < y2 else -1
    err = dx - dy

    h, w = wall_mask.shape[:2]
    while True:
        if 0 <= y1 < h and 0 <= x1 < w:
            if wall_mask[y1, x1] > 127:  # белый = стена
                return False
        if x1 == x2 and y1 == y2:
            break
        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            x1 += sx
        if e2 < dx:
            err += dx
            y1 += sy

    return True


def _los_clear(
    door_xy: tuple[float, float],
    snap_xy: tuple[float, float],
    wall_mask: np.ndarray,
    skip_px: float,
) -> bool:
    """LOS от двери до точки привязки коридора, засеянная на skip_px от двери.

    Центр двери лежит НА (часто запечатанном бинаризацией) дверном проёме —
    т.е. на пикселе-стене, поэтому «сырой» ``_line_of_sight`` упал бы на самом
    первом пикселе. Сдвигаем старт луча на ``skip_px`` в сторону точки привязки,
    за пределы собственной стены проёма, и проверяем оставшуюся часть линии
    (🔴-1: без этого ни одна дверь не привязалась бы → граф без рёбер).
    """
    dx = snap_xy[0] - door_xy[0]
    dy = snap_xy[1] - door_xy[1]
    dist = math.hypot(dx, dy)
    if dist <= skip_px:           # точка привязки внутри «засеянной» зоны → рядом
        return True
    ux, uy = dx / dist, dy / dist
    seed = (door_xy[0] + ux * skip_px, door_xy[1] + uy * skip_px)
    return _line_of_sight(seed, snap_xy, wall_mask)


def attach_unlinked_rooms(
    G: nx.Graph,
    wall_mask: np.ndarray,
    max_attach_px: float,
    skip_px: float,
) -> nx.Graph:
    """Привязывает комнаты вне коридорной компоненты к видимому corridor_node.

    Универсальный fallback Stage B. После
    ``integrate_semantics`` комната без двери (каждая лестница/лифт) остаётся
    синглтон-компонентой ``{'room': 1}`` — маршрутизировать не через что. Для
    каждой такой комнаты луч засевается от КРАЯ её bbox (а не центра — из центра
    LOS всегда упирается в собственную стену, RC1) к каждому ``corridor_node``:
    при чистой видимости (seeded ``_los_clear``) в пределах ``max_attach_px``
    добавляется ребро ``room → corridor_node``. Среди кандидатов предпочитается
    узел в САМОЙ БОЛЬШОЙ компоненте, затем ближайший — чтобы не цепляться к
    шумовому фрагменту, когда магистральный коридор тоже видим.

    Чистая функция: только ``math`` / ``networkx`` + ``_los_clear`` /
    ``_line_of_sight`` этого модуля. Мутирует и возвращает тот же ``G`` (как
    ``bridge_graph_components`` / ``integrate_semantics``). ``wall_mask`` НЕ
    мутируется (Bresenham только читает).

    Args:
        G: граф после ``integrate_semantics``; ``corridor_node`` несут
            ``pos=(x_px, y_px)``, ``room`` — ``pos`` (центр bbox) и
            ``bbox=(rx, ry, rw, rh)`` в пикселях.
        wall_mask: ``(H, W)`` uint8 ``{0,255}`` — белый (> 127) = стена. Та же
            ассемблированная маска, что у ``bridge_graph_components``.
        max_attach_px: максимум дистанции «край bbox → corridor_node» (px).
        skip_px: отступ луча за собственную стену комнаты перед LOS-проверкой
            (px; семантика ``_los_clear``, ``wall_thickness + 1``).

    Returns:
        тот же ``G`` с добавленными рёбрами ``room → corridor_node``
        (``type='room_to_corridor'``, ``attached=True``,
        ``weight=|center−edge|+|edge−node|``, ``pts=[center, edge_pt, node_pos]``).
    """
    t0 = time.perf_counter()

    corridor_nodes = [
        (n, data["pos"])
        for n, data in G.nodes(data=True)
        if data.get("type") == "corridor_node"
    ]
    if not corridor_nodes:           # не к чему привязывать
        return G

    # Компоненты считаем ОДИН раз: целями привязки служат только corridor_node, а
    # непривязанные комнаты целями быть не могут → пересчёт не нужен, результат
    # детерминирован по построению.
    node_comp: dict = {}
    comp_size: list[int] = []
    comp_has_corridor: list[bool] = []
    for idx, comp in enumerate(nx.connected_components(G)):
        comp_size.append(len(comp))
        comp_has_corridor.append(
            any(G.nodes[n].get("type") == "corridor_node" for n in comp)
        )
        for n in comp:
            node_comp[n] = idx

    attached = 0
    unlinked = 0
    for r, data in list(G.nodes(data=True)):
        if data.get("type") != "room":
            continue
        if comp_has_corridor[node_comp[r]]:
            continue                 # уже на коридоре (через дверь) — пропускаем
        bbox = data.get("bbox")
        center = data.get("pos")
        if bbox is None or center is None:
            unlinked += 1
            continue
        rx, ry, rw, rh = bbox

        best_key: tuple[int, float] | None = None
        best_c = None
        best_c_pos = None
        best_edge_pt = None
        best_d_edge = 0.0
        for c, c_pos in corridor_nodes:
            # Ближайшая точка AABB комнаты к узлу коридора (clamp на грань).
            edge_x = min(max(c_pos[0], rx), rx + rw)
            edge_y = min(max(c_pos[1], ry), ry + rh)
            d_edge = math.hypot(edge_x - c_pos[0], edge_y - c_pos[1])
            if d_edge > max_attach_px:
                continue
            # Seeded LOS от грани — настоящий предохранитель против стены.
            if not _los_clear((edge_x, edge_y), c_pos, wall_mask, skip_px):
                continue
            key = (comp_size[node_comp[c]], -d_edge)
            if best_key is None or key > best_key:
                best_key = key
                best_c = c
                best_c_pos = c_pos
                best_edge_pt = (edge_x, edge_y)
                best_d_edge = d_edge

        if best_key is None:
            unlinked += 1
            continue

        weight = (
            math.hypot(center[0] - best_edge_pt[0], center[1] - best_edge_pt[1])
            + best_d_edge
        )
        G.add_edge(
            r, best_c, weight=weight, type="room_to_corridor",
            pts=[center, best_edge_pt, best_c_pos], attached=True,
        )
        attached += 1

    logger.info(
        "attach_unlinked_rooms: +%d attached, %d still unlinked, %.1fms",
        attached, unlinked, (time.perf_counter() - t0) * 1000,
    )
    return G


def simplify_path(
    coords_2d: list[tuple[float, float]],
    dp_epsilon: float = 3.0,
    angle_threshold_deg: float = 5.0,
    min_point_distance: float = 5.0,
) -> list[tuple[float, float]]:
    """
    Упрощает маршрут из пиксельного зигзага в гладкую ломаную.

    Три этапа:
    1. Douglas-Peucker (cv2.approxPolyDP) — основное упрощение
    2. Коллинеарная фильтрация — выпрямление длинных участков
    3. Минимальная дистанция — удаление слишком близких точек
    """
    t0 = time.perf_counter()
    original_count = len(coords_2d)

    if len(coords_2d) < 3:
        return coords_2d

    # Этап 1: Douglas-Peucker
    points_array = np.array(coords_2d, dtype=np.float32).reshape(-1, 1, 2)
    simplified = cv2.approxPolyDP(points_array, epsilon=dp_epsilon, closed=False)
    coords: list[tuple[float, float]] = [(float(pt[0][0]), float(pt[0][1])) for pt in simplified]

    # Этап 2: Коллинеарная фильтрация
    coords = _filter_collinear(coords, angle_threshold_deg)

    # Этап 3: Минимальная дистанция
    coords = _filter_min_distance(coords, min_point_distance)

    logger.info(
        "simplify_path: %d → %d points (%.0f%% reduction), %.1fms",
        original_count, len(coords),
        (1 - len(coords) / max(1, original_count)) * 100,
        (time.perf_counter() - t0) * 1000,
    )

    return coords


def _filter_collinear(
    coords: list[tuple[float, float]],
    angle_threshold_deg: float = 5.0,
) -> list[tuple[float, float]]:
    """Убирает точки, которые почти на одной прямой с соседями."""
    if len(coords) < 3:
        return coords

    threshold_rad = math.radians(angle_threshold_deg)
    result = [coords[0]]

    for i in range(1, len(coords) - 1):
        prev = result[-1]
        curr = coords[i]
        next_pt = coords[i + 1]

        v1 = (curr[0] - prev[0], curr[1] - prev[1])
        v2 = (next_pt[0] - curr[0], next_pt[1] - curr[1])

        len1 = math.hypot(v1[0], v1[1])
        len2 = math.hypot(v2[0], v2[1])

        if len1 < 1e-6 or len2 < 1e-6:
            continue

        cos_angle = (v1[0] * v2[0] + v1[1] * v2[1]) / (len1 * len2)
        cos_angle = max(-1.0, min(1.0, cos_angle))
        angle = math.acos(cos_angle)

        if angle > threshold_rad:
            result.append(curr)

    result.append(coords[-1])
    return result


def _filter_min_distance(
    coords: list[tuple[float, float]],
    min_dist: float = 5.0,
) -> list[tuple[float, float]]:
    """Убирает точки ближе min_dist пикселей к предыдущей."""
    if len(coords) < 2:
        return coords

    result = [coords[0]]
    for pt in coords[1:-1]:
        prev = result[-1]
        if math.hypot(pt[0] - prev[0], pt[1] - prev[1]) >= min_dist:
            result.append(pt)
    result.append(coords[-1])
    return result


def transform_2d_to_3d(
    coords_2d: list[tuple[float, float]],
    mask_width: int,
    mask_height: int,
    scale_factor: float,
    y_offset: float = 0.1,
) -> list[list[float]]:
    """
    Преобразует 2D пиксельные координаты в 3D мировые координаты (Three.js).

    mesh_builder.py строит меш без центрирования, затем применяет поворот
    -90° вокруг X (Z-up → Y-up). После поворота координаты вершины пикселя
    (x_pix, y_pix) оказываются в:
        x_3d = x_pix * S
        z_3d = (y_pix - H) * S   (Y-flip из contours_to_polygons + поворот)

    MeshViewer не центрирует модель — CameraSetup только наводит камеру на
    центр bounding box, сама модель остаётся на своих координатах.
    """
    coords_3d = []
    for (x_pix, y_pix) in coords_2d:
        x_3d = x_pix * scale_factor
        y_3d = y_offset
        z_3d = (y_pix - mask_height) * scale_factor
        coords_3d.append([round(x_3d, 4), round(y_3d, 4), round(z_3d, 4)])
    return coords_3d


# Floor Transitions — multifloor graph merge and routing

from dataclasses import dataclass  # noqa: E402 (stdlib, safe here)

FLOOR_HEIGHT_METERS: float = 3.5  # Height per floor for 3D coordinates


@dataclass
class FloorGraphData:
    """Holds a single floor's graph plus metadata needed for merge/route."""

    graph: nx.Graph
    metadata: dict          # mask_width, mask_height, scale_factor
    reconstruction_id: int
    floor_number: int       # from Reconstruction.floor_number
    floor_name: str         # from Reconstruction.name


def _find_nearest_node(
    G: nx.Graph,
    recon_id: int,
    target_px: float,
    target_py: float,
    max_distance_px: float = 200.0,
) -> str | None:
    """Return the prefixed node id closest to (target_px, target_py) within max_distance_px."""
    best_node: str | None = None
    best_dist = max_distance_px

    prefix = f"{recon_id}:"
    for node_id, data in G.nodes(data=True):
        if not str(node_id).startswith(prefix):
            continue
        pos = data.get("pos")
        if pos is None:
            continue
        dist = math.hypot(pos[0] - target_px, pos[1] - target_py)
        if dist < best_dist:
            best_dist = dist
            best_node = node_id

    return best_node


def merge_floor_graphs(
    floor_data: list[FloorGraphData],
    transition_groups: list[dict],
) -> tuple[nx.Graph, dict[int, FloorGraphData]]:
    """
    Merge N floor graphs into one, connecting them via transition edges.

    Args:
        floor_data: list of FloorGraphData (one per floor/reconstruction)
        transition_groups: list of dicts representing transition groups
            keys: id, name, type, points
            where points is a list of dicts: id, reconstruction_id, x, y

    Returns:
        (merged_graph, floor_data_by_recon_id)
        All nodes are prefixed with "{recon_id}:{original_node_id}".
    """
    merged = nx.Graph()
    floor_data_by_recon_id: dict[int, FloorGraphData] = {}

    # Copy all nodes and edges with recon_id prefix
    for fd in floor_data:
        floor_data_by_recon_id[fd.reconstruction_id] = fd
        prefix = f"{fd.reconstruction_id}:"
        for node_id, data in fd.graph.nodes(data=True):
            new_id = f"{prefix}{node_id}"
            merged.add_node(new_id, recon_id=fd.reconstruction_id, **data)
        for u, v, edge_data in fd.graph.edges(data=True):
            merged.add_edge(f"{prefix}{u}", f"{prefix}{v}", **edge_data)

    # Add transition edges
    for group in transition_groups:
        group_id = group["id"]
        group_name = group["name"]
        points = group.get("points", [])

        valid_points = []
        for p in points:
            recon_id = p["reconstruction_id"]
            fd = floor_data_by_recon_id.get(recon_id)
            if fd is None:
                continue

            meta = fd.metadata
            px = p["x"] * meta.get("mask_width", 1)
            py = p["y"] * meta.get("mask_height", 1)

            nearest = _find_nearest_node(merged, recon_id, px, py)
            if nearest is None:
                continue

            pos = merged.nodes[nearest].get("pos", (px, py))
            teleport_id = f"teleport_{group_id}_pt_{p['id']}"

            merged.add_node(
                teleport_id,
                type="teleport",
                pos=pos,
                recon_id=recon_id,
                transition_id=group_id,
                transition_name=group_name,
            )
            merged.add_edge(nearest, teleport_id, weight=5.0, type="teleport_approach")

            valid_points.append(teleport_id)

        # Create a fully connected mesh between all valid points in this group
        for i in range(len(valid_points)):
            for j in range(i + 1, len(valid_points)):
                merged.add_edge(
                    valid_points[i], valid_points[j],
                    weight=10.0,
                    type="floor_transition",
                    transition_name=group_name,
                    transition_id=group_id,
                )

    return merged, floor_data_by_recon_id


def find_multifloor_route_in_graph(
    merged_graph: nx.Graph,
    floor_data_by_recon_id: dict[int, FloorGraphData],
    from_recon_id: int,
    from_room_id: str,
    to_recon_id: int,
    to_room_id: str,
) -> dict | None:
    """
    A* search in the merged graph between room nodes on (possibly different) floors.

    Returns:
        dict with keys: status, path_segments, transitions_used, total_distance_px
        or None if no path found.

    path_segments: list of {reconstruction_id, floor_number, floor_name, coords_2d}
    transitions_used: list of {name, from_px, to_px, from_recon_id, to_recon_id}
    """
    from_node_id = f"{from_recon_id}:room_{from_room_id}"
    to_node_id = f"{to_recon_id}:room_{to_room_id}"

    if from_node_id not in merged_graph.nodes:
        logger.warning("find_multifloor_route_in_graph: from node %s not in graph", from_node_id)
        return None
    if to_node_id not in merged_graph.nodes:
        logger.warning("find_multifloor_route_in_graph: to node %s not in graph", to_node_id)
        return None

    if not nx.has_path(merged_graph, from_node_id, to_node_id):
        return None

    def heuristic(u: str, v: str) -> float:
        u_pos = merged_graph.nodes[u].get("pos", (0.0, 0.0))
        v_pos = merged_graph.nodes[v].get("pos", (0.0, 0.0))
        return math.hypot(u_pos[0] - v_pos[0], u_pos[1] - v_pos[1])

    try:
        path_nodes = nx.astar_path(
            merged_graph, from_node_id, to_node_id,
            heuristic=heuristic, weight="weight",
        )
    except nx.NetworkXNoPath:
        return None

    # Compute total distance
    total_distance_px = 0.0
    for i in range(len(path_nodes) - 1):
        edge_data = merged_graph.get_edge_data(path_nodes[i], path_nodes[i + 1]) or {}
        total_distance_px += edge_data.get("weight", 0.0)

    # Group nodes by recon_id into segments, collect transitions
    segments: dict[int, list[tuple[float, float]]] = {}
    segment_order: list[int] = []
    transitions_used: list[dict] = []

    for node_id in path_nodes:
        node_data = merged_graph.nodes[node_id]
        recon_id = node_data.get("recon_id")
        if recon_id is None:
            continue
        pos = node_data.get("pos")
        if pos is None:
            continue
        if recon_id not in segments:
            segments[recon_id] = []
            segment_order.append(recon_id)
        segments[recon_id].append((float(pos[0]), float(pos[1])))

    # Collect floor_transition edges
    for i in range(len(path_nodes) - 1):
        edge_data = merged_graph.get_edge_data(path_nodes[i], path_nodes[i + 1]) or {}
        if edge_data.get("type") == "floor_transition":
            from_pos = merged_graph.nodes[path_nodes[i]].get("pos", (0.0, 0.0))
            to_pos = merged_graph.nodes[path_nodes[i + 1]].get("pos", (0.0, 0.0))
            from_rid = merged_graph.nodes[path_nodes[i]].get("recon_id")
            to_rid = merged_graph.nodes[path_nodes[i + 1]].get("recon_id")
            transitions_used.append({
                "name": edge_data.get("transition_name", ""),
                "from_px": (float(from_pos[0]), float(from_pos[1])),
                "to_px": (float(to_pos[0]), float(to_pos[1])),
                "from_recon_id": from_rid,
                "to_recon_id": to_rid,
            })

    # Build path_segments list
    path_segments = []
    for recon_id in segment_order:
        fd = floor_data_by_recon_id.get(recon_id)
        if fd is None:
            continue
        path_segments.append({
            "reconstruction_id": recon_id,
            "floor_number": fd.floor_number,
            "floor_name": fd.floor_name,
            "coords_2d": segments[recon_id],
        })

    return {
        "status": "success",
        "path_segments": path_segments,
        "transitions_used": transitions_used,
        "total_distance_px": total_distance_px,
    }
