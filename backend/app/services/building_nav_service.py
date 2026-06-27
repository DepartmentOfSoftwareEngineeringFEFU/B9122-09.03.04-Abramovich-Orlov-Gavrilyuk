"""Межэтажная маршрутизация и проверка связей между этажами.

Загружает сохранённый навиграф каждого этажа и его building_transform, строит
сквозной маршрут в общей системе координат здания и хранит ручные правки связей
переходов (transition_overrides).

Точка маршрута на этаже F размещается в [X_m, elevation_m(F) + 0.1,
Y_m - ref_height_m], где (X_m, Y_m) это проекция в метры опорного этажа, а
ref_height_m = ref_mask_h / ppm_ref.
"""

import json
import logging
import math
import os
from typing import Optional

import cv2

from app.core.exceptions import (
    BuildingNotFoundError,
    FloorNavGraphNotFoundError,
    FloorNotFoundError,
)
from app.core.floor_stitching_constants import (
    FLOOR_HEIGHT,
    INTER_FLOOR_GAP_M,
    MATCH_TOLERANCE_M,
    TRANSITION_COST_M,
)
from app.db.repositories.building_repo import BuildingRepository
from app.db.repositories.floor_repo import FloorRepository
from app.models.building_nav import (
    FloorPathSegment3D,
    MultifloorRouteResponse,
    SaveTransitionLinksResponse,
    TransitionLink,
    TransitionLinksResponse,
    TransitionOverride,
    TransitionUsed3D,
    UnmatchedTransition,
)
from app.processing.multifloor_graph import (
    FloorRouteEntry,
    TransitionLink as ProcLink,
    TransitionNode,
    find_multifloor_route_by_id,
    match_cross_floor_transitions,
    merge_floor_graphs_by_id,
    project_to_building_frame,
    transition_nodes_from_entry,
)
from app.processing.nav_graph import deserialize_nav_graph, find_route, los_prune
from app.services.file_storage import FileStorage

logger = logging.getLogger(__name__)

_NOT_ALIGNED_MSG = "Этажи не выровнены, выполните сборку здания"
_WALK_SPEED_MS = 1.2  # м/с, как в nav_service


def _is_positive_finite(value: Optional[float]) -> bool:
    """Число конечное и строго положительное."""
    return value is not None and math.isfinite(value) and value > 0


class BuildingNavService:
    """Межэтажная маршрутизация и управление связями переходов."""

    def __init__(
        self,
        building_repo: BuildingRepository,
        floor_repo: FloorRepository,
        storage: FileStorage,
        upload_dir: str,
    ) -> None:
        self._building_repo = building_repo
        self._floor_repo = floor_repo
        self._storage = storage
        self._nav_dir = os.path.join(upload_dir, "nav")

    async def find_multifloor_route(
        self,
        building_id: int,
        from_floor_id: int,
        from_room: str,
        to_floor_id: int,
        to_room: str,
    ) -> MultifloorRouteResponse:
        """Найти кратчайший межэтажный маршрут как 3D-ломаную в координатах здания.

        Статус ответа: success, no_path или not_aligned.
        """
        logger.info(
            "find_multifloor_route: b=%d %d:%s → %d:%s",
            building_id, from_floor_id, from_room, to_floor_id, to_room,
        )
        building = await self._building_repo.get_by_id(building_id)
        if building is None:
            raise BuildingNotFoundError(building_id)

        floors = await self._floor_repo.list_by_building(building_id)
        if not floors:
            return MultifloorRouteResponse(
                status="no_path", message="В здании нет этажей"
            )
        floor_by_id = {f.id: f for f in floors}
        for fid in (from_floor_id, to_floor_id):
            if fid not in floor_by_id:
                raise FloorNotFoundError(fid)

        ref = floors[0]  # отсортировано по number, первый это нижний этаж
        min_number = ref.number
        ppm_ref = ref.pixels_per_meter
        if not _is_positive_finite(ppm_ref):
            return MultifloorRouteResponse(
                status="not_aligned", message=_NOT_ALIGNED_MSG
            )
        ref_dims = self._floor_mask_dims(ref)
        if ref_dims is None:
            raise ValueError("floor mask dims unavailable for reference floor")
        ref_height_m = ref_dims[1] / ppm_ref

        for fid in (from_floor_id, to_floor_id):
            if not self._has_graph(fid):
                raise FloorNavGraphNotFoundError(fid)

        # Сначала пробуем маршрут в пределах одного этажа: он дешевле и спрямляется
        # по маске. Если концы лежат в несвязанных частях этажа (например, два крыла,
        # соединённые только проходом на другом этаже), переходим к межэтажному графу
        # ниже, который умеет обойти через лестницу и другой этаж. Переходим только
        # при no_path; отсутствие комнаты по-прежнему даёт ошибку.
        if from_floor_id == to_floor_id:
            floor = floor_by_id[from_floor_id]
            if not self._is_aligned(floor, ref.id):
                return MultifloorRouteResponse(
                    status="not_aligned", message=_NOT_ALIGNED_MSG
                )
            entry = self._load_floor_entry(floor, min_number)
            single = self._single_floor_response(
                entry, from_room, to_room, ppm_ref, ref_height_m
            )
            if single.status == "success":
                return single

        # Межэтажный случай: грузим все этажи с графом, все должны быть выровнены.
        entries: list[FloorRouteEntry] = []
        for floor in floors:
            if not self._has_graph(floor.id):
                continue
            if not self._is_aligned(floor, ref.id):
                return MultifloorRouteResponse(
                    status="not_aligned", message=_NOT_ALIGNED_MSG
                )
            entries.append(self._load_floor_entry(floor, min_number))

        overrides = building.transition_overrides or []
        links = self._final_links_for_merge(entries, ppm_ref, overrides)
        merged = merge_floor_graphs_by_id(entries, links, TRANSITION_COST_M, ppm_ref)
        route = find_multifloor_route_by_id(
            merged, from_floor_id, from_room, to_floor_id, to_room
        )
        if route["status"] == "no_path":
            return MultifloorRouteResponse(
                status="no_path", message="Маршрут между этажами не найден"
            )

        entry_by_id = {e.floor_id: e for e in entries}
        segments: list[FloorPathSegment3D] = []
        for seg in route["path_segments"]:
            entry = entry_by_id.get(seg["floor_id"])
            if entry is None:
                continue
            segments.append(
                FloorPathSegment3D(
                    floor_id=seg["floor_id"],
                    floor_number=seg["floor_number"],
                    coordinates_3d=self._project_segment(
                        seg["coords_2d"], entry, ppm_ref, ref_height_m
                    ),
                )
            )

        transitions: list[TransitionUsed3D] = []
        for tr in route["transitions_used"]:
            fe = entry_by_id.get(tr["from_floor_id"])
            te = entry_by_id.get(tr["to_floor_id"])
            if fe is None or te is None or tr["from_pos"] is None or tr["to_pos"] is None:
                continue
            transitions.append(
                TransitionUsed3D(
                    type=tr["type"],
                    from_3d=self._project_point(tr["from_pos"], fe, ppm_ref, ref_height_m),
                    to_3d=self._project_point(tr["to_pos"], te, ppm_ref, ref_height_m),
                    from_floor_id=tr["from_floor_id"],
                    to_floor_id=tr["to_floor_id"],
                    from_node=tr.get("from_node", ""),
                    to_node=tr.get("to_node", ""),
                )
            )

        total_m = float(route["total_distance_m"])
        return MultifloorRouteResponse(
            status="success",
            total_distance_meters=round(total_m, 2),
            estimated_time_seconds=self._eta_seconds(total_m),
            path_segments=segments,
            transitions_used=transitions,
        )

    async def list_links(self, building_id: int) -> TransitionLinksResponse:
        """Вернуть автоматически найденные межэтажные связи с учётом правок."""
        logger.debug("list_links: building_id=%d", building_id)
        building = await self._building_repo.get_by_id(building_id)
        if building is None:
            raise BuildingNotFoundError(building_id)

        floors = await self._floor_repo.list_by_building(building_id)
        if not floors:
            return TransitionLinksResponse(building_id=building_id, status="not_aligned")
        ref = floors[0]
        ppm_ref = ref.pixels_per_meter
        if not _is_positive_finite(ppm_ref):
            return TransitionLinksResponse(building_id=building_id, status="not_aligned")
        number_by_id = {f.id: f.number for f in floors}

        entries: list[FloorRouteEntry] = []
        for floor in floors:
            if not self._has_graph(floor.id):
                continue
            if not self._is_aligned(floor, ref.id):
                return TransitionLinksResponse(
                    building_id=building_id, status="not_aligned"
                )
            entries.append(self._load_floor_entry(floor, ref.number))

        nodes = self._all_transition_nodes(entries, ppm_ref)
        auto, unmatched = match_cross_floor_transitions(nodes, MATCH_TOLERANCE_M)
        index = {(n.floor_id, n.node_id): n for n in nodes}
        overrides = building.transition_overrides or []
        disabled = {self._okey(o) for o in overrides if o.get("action") == "disable"}

        links: list[TransitionLink] = []
        auto_keys: set[tuple] = set()
        for lk in auto:
            key = (lk.lower_floor_id, lk.lower_node, lk.upper_floor_id, lk.upper_node)
            auto_keys.add(key)
            links.append(
                self._to_api_link(
                    lk, number_by_id, source="auto", enabled=(key not in disabled)
                )
            )
        for ovr in overrides:
            if ovr.get("action") != "force":
                continue
            key = self._okey(ovr)
            if key in auto_keys:
                continue  # принудительная связь поверх автоматической ничего не меняет
            forced = self._build_forced_link(ovr, index)
            if forced is None:
                continue
            links.append(
                self._to_api_link(forced, number_by_id, source="forced", enabled=True)
            )

        return TransitionLinksResponse(
            building_id=building_id,
            links=links,
            unmatched=[
                UnmatchedTransition(
                    floor_id=u.floor_id,
                    floor_number=u.floor_number,
                    node=u.node,
                    type=u.type,
                    reason=u.reason,
                )
                for u in unmatched
            ],
        )

    async def save_overrides(
        self, building_id: int, overrides: list[TransitionOverride]
    ) -> SaveTransitionLinksResponse:
        """Сохранить весь набор правок, проверив ссылки принудительных связей."""
        logger.info(
            "save_overrides: building_id=%d, count=%d", building_id, len(overrides)
        )
        building = await self._building_repo.get_by_id(building_id)
        if building is None:
            raise BuildingNotFoundError(building_id)

        forced = [o for o in overrides if o.action == "force"]
        if forced:
            floors = await self._floor_repo.list_by_building(building_id)
            ppm_ref = floors[0].pixels_per_meter if floors else None
            index: dict[tuple[int, str], TransitionNode] = {}
            if floors and _is_positive_finite(ppm_ref):
                entries = [
                    self._load_floor_entry(f, floors[0].number)
                    for f in floors
                    if self._has_graph(f.id)
                ]
                index = {
                    (n.floor_id, n.node_id): n
                    for n in self._all_transition_nodes(entries, ppm_ref)
                }
            for ovr in forced:
                lo = index.get((ovr.lower_floor_id, ovr.lower_node))
                hi = index.get((ovr.upper_floor_id, ovr.upper_node))
                if lo is None or hi is None:
                    raise ValueError(
                        "force override references a node not in the graph"
                    )
                if lo.room_type != hi.room_type:
                    raise ValueError("force override links different transition types")

        await self._building_repo.update(
            building_id, transition_overrides=[o.model_dump() for o in overrides]
        )
        return SaveTransitionLinksResponse(
            building_id=building_id, overrides_count=len(overrides)
        )

    @staticmethod
    def _all_transition_nodes(
        entries: list[FloorRouteEntry], ppm_ref: float
    ) -> list[TransitionNode]:
        """Собрать спроецированные узлы лестниц и лифтов со всех этажей."""
        nodes: list[TransitionNode] = []
        for entry in entries:
            nodes.extend(transition_nodes_from_entry(entry, ppm_ref))
        return nodes

    def _final_links_for_merge(
        self,
        entries: list[FloorRouteEntry],
        ppm_ref: float,
        overrides: list[dict],
    ) -> list[ProcLink]:
        """Итоговый набор связей: автоматические минус отключённые плюс принудительные."""
        nodes = self._all_transition_nodes(entries, ppm_ref)
        auto, _ = match_cross_floor_transitions(nodes, MATCH_TOLERANCE_M)
        index = {(n.floor_id, n.node_id): n for n in nodes}
        disabled = {self._okey(o) for o in overrides if o.get("action") == "disable"}
        final = [
            lk
            for lk in auto
            if (lk.lower_floor_id, lk.lower_node, lk.upper_floor_id, lk.upper_node)
            not in disabled
        ]
        for ovr in overrides:
            if ovr.get("action") != "force":
                continue
            forced = self._build_forced_link(ovr, index)
            if forced is not None:
                final.append(forced)
        return final

    @staticmethod
    def _okey(ovr: dict) -> tuple:
        """Ключ правки: нижний и верхний этаж с узлами."""
        return (
            ovr.get("lower_floor_id"),
            ovr.get("lower_node"),
            ovr.get("upper_floor_id"),
            ovr.get("upper_node"),
        )

    @staticmethod
    def _build_forced_link(
        ovr: dict, index: dict[tuple[int, str], TransitionNode]
    ) -> Optional[ProcLink]:
        """Построить принудительный ProcLink из правки, либо None если данные неверны."""
        lo = index.get((ovr.get("lower_floor_id"), ovr.get("lower_node")))
        hi = index.get((ovr.get("upper_floor_id"), ovr.get("upper_node")))
        if lo is None or hi is None:
            return None
        d = math.hypot(lo.x_m - hi.x_m, lo.y_m - hi.y_m)
        return ProcLink(
            lower_floor_id=lo.floor_id,
            lower_node=lo.node_id,
            upper_floor_id=hi.floor_id,
            upper_node=hi.node_id,
            type=lo.room_type,
            source="forced",
            distance_m=round(d, 4),
        )

    @staticmethod
    def _to_api_link(
        lk: ProcLink,
        number_by_id: dict[int, int],
        source: str,
        enabled: bool,
    ) -> TransitionLink:
        """Преобразовать ProcLink в TransitionLink для API, добавив номера этажей."""
        return TransitionLink(
            lower_floor_id=lk.lower_floor_id,
            lower_floor_number=number_by_id.get(lk.lower_floor_id, 0),
            lower_node=lk.lower_node,
            upper_floor_id=lk.upper_floor_id,
            upper_floor_number=number_by_id.get(lk.upper_floor_id, 0),
            upper_node=lk.upper_node,
            type=lk.type,
            source=source,
            enabled=enabled,
            distance_m=lk.distance_m,
        )

    def _single_floor_response(
        self,
        entry: FloorRouteEntry,
        from_room: str,
        to_room: str,
        ppm_ref: float,
        ref_height_m: float,
    ) -> MultifloorRouteResponse:
        """Построить маршрут в пределах одного этажа в координатах здания."""
        graph = entry.graph
        fn = from_room if from_room.startswith("room_") else f"room_{from_room}"
        tn = to_room if to_room.startswith("room_") else f"room_{to_room}"
        for node, raw in ((fn, from_room), (tn, to_room)):
            if node not in graph.nodes:
                raise ValueError(f"Комната '{raw}' не найдена в графе")

        route = find_route(graph, fn, tn)
        if route is None:
            return MultifloorRouteResponse(
                status="no_path", message="Маршрут на этаже не найден"
            )
        coords_3d = self._project_segment(
            route["path_coords_2d"], entry, ppm_ref, ref_height_m
        )
        total_m = float(route["total_distance_px"]) * entry.scale_factor
        return MultifloorRouteResponse(
            status="success",
            total_distance_meters=round(total_m, 2),
            estimated_time_seconds=self._eta_seconds(total_m),
            path_segments=[
                FloorPathSegment3D(
                    floor_id=entry.floor_id,
                    floor_number=entry.floor_number,
                    coordinates_3d=coords_3d,
                )
            ],
            transitions_used=[],
        )

    def _project_segment(
        self,
        coords_2d: list,
        entry: FloorRouteEntry,
        ppm_ref: float,
        ref_height_m: float,
    ) -> list[list[float]]:
        """Спрямить путь по видимости и спроецировать 2D-путь этажа в 3D."""
        pruned = self._maybe_los_prune(coords_2d, entry)
        return [
            self._project_point(pt, entry, ppm_ref, ref_height_m) for pt in pruned
        ]

    def _project_point(
        self,
        pos_canvas,
        entry: FloorRouteEntry,
        ppm_ref: float,
        ref_height_m: float,
    ) -> list[float]:
        """Перевести точку в пикселях канваса в мировые координаты здания."""
        k = entry.nav_mask_w / entry.floor_mask_w if entry.floor_mask_w else 0.0
        x_m, y_m = project_to_building_frame(
            (float(pos_canvas[0]), float(pos_canvas[1])),
            k,
            entry.building_transform,
            ppm_ref,
        )
        return [
            round(x_m, 4),
            round(entry.elevation_m + 0.1, 4),
            round(y_m - ref_height_m, 4),
        ]

    def _maybe_los_prune(self, coords_2d: list, entry: FloorRouteEntry) -> list:
        """Спрямление пути по маске этажа, если она доступна.

        Проверка shape нужна для безопасности: los_prune считает точки за границей
        не стеной, поэтому устаревшая или меньшая маска могла бы пройти сквозь стену.
        Если маски нет или размеры не совпадают, путь возвращается как есть.
        """
        try:
            mask = cv2.imread(
                self._floor_mask_path(entry.floor_id), cv2.IMREAD_GRAYSCALE
            )
            if mask is not None and mask.shape == (entry.nav_mask_h, entry.nav_mask_w):
                return los_prune(coords_2d, mask)
        except Exception:
            pass
        return coords_2d

    @staticmethod
    def _eta_seconds(distance_m: float) -> int:
        """Время в пути при скорости 1.2 м/с."""
        return int(round(distance_m / _WALK_SPEED_MS)) if distance_m else 0

    @staticmethod
    def _is_aligned(floor, reference_floor_id: int) -> bool:  # type: ignore[no-untyped-def]
        """Этаж выровнен, если он опорный или у него есть building_transform."""
        return floor.id == reference_floor_id or floor.building_transform is not None

    def _nav_path(self, floor_id: int) -> str:
        return os.path.join(self._nav_dir, f"floor_{floor_id}_nav.json")

    def _floor_mask_path(self, floor_id: int) -> str:
        return os.path.join(self._nav_dir, f"floor_{floor_id}_mask.png")

    def _has_graph(self, floor_id: int) -> bool:
        return os.path.exists(self._nav_path(floor_id))

    def _load_floor_entry(  # type: ignore[no-untyped-def]
        self, floor, min_number: int
    ) -> FloorRouteEntry:
        """Загрузить навиграф и размеры этажа в FloorRouteEntry.

        Предполагает, что граф уже построен (проверяет вызывающий код). Бросает
        ValueError, если размеры маски этажа недоступны.
        """
        with open(self._nav_path(floor.id)) as f:
            graph, meta = deserialize_nav_graph(json.load(f))
        dims = self._floor_mask_dims(floor)
        if dims is None:
            raise ValueError(
                f"floor mask dims unavailable for floor {floor.id}"
            )
        return FloorRouteEntry(
            floor_id=floor.id,
            floor_number=floor.number,
            graph=graph,
            scale_factor=meta["scale_factor"],
            nav_mask_w=meta["mask_width"],
            nav_mask_h=meta["mask_height"],
            floor_mask_w=dims[0],
            floor_mask_h=dims[1],
            building_transform=floor.building_transform,
            # Тот же шаг по высоте, что и при размещении GLB этажа, чтобы маршрут
            # шёл поверх меша этажа, а не внутри плиты.
            elevation_m=(floor.number - min_number) * (FLOOR_HEIGHT + INTER_FLOOR_GAP_M),
        )

    def _floor_mask_dims(self, floor) -> Optional[tuple[int, int]]:  # type: ignore[no-untyped-def]
        """Размеры маски этажа (W, H), либо None если маски нет или файл отсутствует.

        Нечитаемый файл это ImageProcessingError.
        """
        from app.core.exceptions import FileStorageError, ImageProcessingError

        mask_file_id = getattr(floor, "mask_file_id", None)
        if not mask_file_id:
            return None
        try:
            mask_path = self._storage.find_file(mask_file_id, "masks")
        except FileStorageError:
            return None
        image = cv2.imread(mask_path, cv2.IMREAD_GRAYSCALE)
        if image is None:
            raise ImageProcessingError(
                "floor_mask_dims", f"Failed to read floor mask: {mask_path}"
            )
        h, w = image.shape[:2]
        return (w, h)
