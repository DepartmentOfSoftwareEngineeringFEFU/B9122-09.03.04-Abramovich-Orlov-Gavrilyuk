"""Вертикальная сшивка этажей: сохранение опорных точек, решение и чтение сборки.

building_transform переводит пиксели маски этажа в пиксели маски нижнего
(опорного) этажа; у самого нижнего этажа это тождественное преобразование,
None означает, что этаж ещё не выровнен. Денормализация делается по размерам
маски каждого этажа отдельно.
"""

import logging
import math
from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np

from app.core.exceptions import (
    BuildingNotFoundError,
    FileStorageError,
    FloorAssemblyConflictError,
    FloorNotFoundError,
    ImageProcessingError,
)
from app.core.floor_stitching_constants import (
    FLOOR_HEIGHT,
    MIN_CONTROL_POINTS,
    R_MIN_BASELINE_FRAC,
)
from app.db.repositories.building_repo import BuildingRepository
from app.db.repositories.floor_repo import FloorRepository
from app.models.building_assembly import (
    AssemblyFloor,
    BuildingAssemblyResponse,
    ControlPoint,
    FloorStitchStatus,
    SaveStitchPointsResponse,
    SolveStitchResponse,
    StitchTransform,
)
from app.processing.floor_stack import (
    SimilarityT,
    compose_chain_transforms,
    identity,
)
from app.processing.registration import (
    DegenerateControlPointsError,
    solve_similarity,
)
from app.services.file_storage import FileStorage

logger = logging.getLogger(__name__)


@dataclass
class _PairSolve:
    """Результат решения для одного этажа, накапливается в памяти до записи в БД."""

    floor_id: int
    number: int
    status: str
    pair_transform: Optional[SimilarityT]
    residual_rms_px: float
    n_points: int
    pixels_per_meter: Optional[float]


class BuildingAssemblyService:
    """Сшивка этажей по вертикали на уровне здания."""

    def __init__(
        self,
        building_repo: BuildingRepository,
        floor_repo: FloorRepository,
        storage: FileStorage,
    ) -> None:
        self._building_repo = building_repo
        self._floor_repo = floor_repo
        self._storage = storage

    async def save_stitch_points(
        self,
        floor_id: int,
        points: list[ControlPoint],
        ref_points: list[ControlPoint],
    ) -> SaveStitchPointsResponse:
        """Сохранить опорные точки пары: этот этаж и этаж ниже.

        Этаж не должен быть самым нижним в здании, иначе ссылаться не на что.
        """
        logger.info(
            "save_stitch_points: floor_id=%d, points=%d, ref_points=%d",
            floor_id,
            len(points),
            len(ref_points),
        )
        floor = await self._floor_repo.get_by_id(floor_id)
        if floor is None:
            raise FloorNotFoundError(floor_id)

        siblings = await self._floor_repo.list_by_building(floor.building_id)
        min_number = min(f.number for f in siblings)
        if floor.number == min_number:
            raise FloorAssemblyConflictError(
                "Floor is the lowest in its building — no floor below to reference"
            )

        await self._floor_repo.update_stitch_points(
            floor_id,
            [p.model_dump() for p in points],
            [p.model_dump() for p in ref_points],
        )

        return SaveStitchPointsResponse(
            floor_id=floor_id,
            points_count=len(points),
            ref_points_count=len(ref_points),
        )

    async def solve_stitch(self, building_id: int) -> SolveStitchResponse:
        """Решить каждую соседнюю пару и собрать преобразования всех этажей.

        Сначала выполняются все вычисления в память, и только потом результат
        записывается в БД, чтобы здание не осталось наполовину решённым. Ожидаемые
        сбои пары (мало точек, вырождение, нет маски) отражаются статусом, а не
        исключением.
        """
        logger.info("solve_stitch: building_id=%d", building_id)
        building = await self._building_repo.get_by_id(building_id)
        if building is None:
            raise BuildingNotFoundError(building_id)

        floors = await self._floor_repo.list_by_building(building_id)
        if len(floors) < 2:
            raise FloorAssemblyConflictError("Building needs >= 2 floors to stitch")

        min_number = floors[0].number  # список отсортирован по number по возрастанию
        reference_floor_id = floors[0].id

        mask_dims: list[Optional[tuple[int, int]]] = [
            self._floor_mask_dims(f) for f in floors
        ]

        solves: list[_PairSolve] = [
            _PairSolve(
                floor_id=floors[0].id,
                number=floors[0].number,
                status="reference",
                pair_transform=identity(),
                residual_rms_px=0.0,
                n_points=0,
                pixels_per_meter=floors[0].pixels_per_meter,
            )
        ]

        for i in range(1, len(floors)):
            upper = floors[i]
            lower = floors[i - 1]
            solves.append(
                self._solve_pair(
                    upper=upper,
                    lower=lower,
                    upper_dims=mask_dims[i],
                    lower_dims=mask_dims[i - 1],
                )
            )

        pair_transforms: list[Optional[SimilarityT]] = [
            s.pair_transform for s in solves[1:]
        ]
        composed = compose_chain_transforms(pair_transforms, n_floors=len(floors))

        for floor, comp in zip(floors, composed):
            await self._floor_repo.update_building_transform(
                floor.id, self._similarity_to_dict(comp, floor, solves)
            )

        statuses: list[FloorStitchStatus] = []
        for solve, comp in zip(solves, composed):
            transform = self._build_stitch_transform(comp, solve)
            residual_m = self._residual_in_metres(solve)
            statuses.append(
                FloorStitchStatus(
                    floor_id=solve.floor_id,
                    number=solve.number,
                    status=solve.status,  # type: ignore[arg-type]
                    building_transform=transform,
                    residual_rms_m=residual_m,
                    elevation_m=(solve.number - min_number) * FLOOR_HEIGHT,
                )
            )

        return SolveStitchResponse(
            building_id=building_id,
            reference_floor_id=reference_floor_id,
            floors=statuses,
        )

    def _solve_pair(
        self,
        upper,  # type: ignore[no-untyped-def]
        lower,  # type: ignore[no-untyped-def]
        upper_dims: Optional[tuple[int, int]],
        lower_dims: Optional[tuple[int, int]],
    ) -> _PairSolve:
        """Решить одну соседнюю пару (верхний к нижнему), без записи в БД.

        Точки верхнего этажа денормализуются по размерам его маски, опорные точки
        по размерам маски нижнего этажа.
        """
        base = _PairSolve(
            floor_id=upper.id,
            number=upper.number,
            status="needs_points",
            pair_transform=None,
            residual_rms_px=0.0,
            n_points=0,
            pixels_per_meter=upper.pixels_per_meter,
        )

        if upper_dims is None or lower_dims is None:
            base.status = "no_mask"
            return base

        upper_local = self._points_by_id(upper.stitch_points)
        lower_local = self._points_by_id(upper.stitch_ref_points)
        matched_ids = [pid for pid in upper_local if pid in lower_local]

        if len(matched_ids) < MIN_CONTROL_POINTS:
            base.status = "needs_points"
            return base

        w_u, h_u = upper_dims
        w_l, h_l = lower_dims
        src = np.array(
            [
                [upper_local[pid][0] * w_u, upper_local[pid][1] * h_u]
                for pid in matched_ids
            ],
            dtype=np.float64,
        )
        dst = np.array(
            [
                [lower_local[pid][0] * w_l, lower_local[pid][1] * h_l]
                for pid in matched_ids
            ],
            dtype=np.float64,
        )

        min_baseline_px = R_MIN_BASELINE_FRAC * math.hypot(w_u, h_u)
        try:
            result = solve_similarity(src, dst, min_baseline_px)
        except DegenerateControlPointsError as exc:
            logger.info("pair upper floor %d degenerate: %s", upper.id, exc.reason)
            base.status = "degenerate"
            return base

        base.status = "ok"
        base.pair_transform = SimilarityT(
            scale=result.scale,
            rotation_rad=result.rotation_rad,
            tx=result.tx,
            ty=result.ty,
        )
        base.residual_rms_px = result.residual_rms
        base.n_points = result.n_points
        return base

    async def get_assembly(self, building_id: int) -> BuildingAssemblyResponse:
        """Прочитать состояние сборки для страницы сборки здания.

        Этажи перечитываются через get_by_id, чтобы подтянуть mask_file для URL.
        """
        logger.debug("get_assembly: building_id=%d", building_id)
        building = await self._building_repo.get_by_id(building_id)
        if building is None:
            raise BuildingNotFoundError(building_id)

        floor_rows = await self._floor_repo.list_by_building(building_id)
        if not floor_rows:
            return BuildingAssemblyResponse(
                building_id=building_id,
                reference_floor_id=None,
                floors=[],
            )

        min_number = floor_rows[0].number
        reference_floor_id = floor_rows[0].id

        assembly_floors: list[AssemblyFloor] = []
        for floor in floor_rows:
            detailed = await self._floor_repo.get_by_id(floor.id)
            row = detailed if detailed is not None else floor
            dims = self._floor_mask_dims(row)
            mask_w = dims[0] if dims else None
            mask_h = dims[1] if dims else None
            transform = (
                StitchTransform(**row.building_transform)
                if row.building_transform
                else None
            )
            assembly_floors.append(
                AssemblyFloor(
                    id=row.id,
                    number=row.number,
                    mask_url=self._floor_mask_url(row),
                    mask_width=mask_w,
                    mask_height=mask_h,
                    pixels_per_meter=row.pixels_per_meter,
                    elevation_m=(row.number - min_number) * FLOOR_HEIGHT,
                    points_count=len(row.stitch_points or []),
                    ref_points_count=len(row.stitch_ref_points or []),
                    points=self._stored_points(row.stitch_points),
                    ref_points=self._stored_points(row.stitch_ref_points),
                    building_transform=transform,
                    pair_status=self._pair_status(
                        row,
                        is_reference=(row.id == reference_floor_id),
                        has_mask=dims is not None,
                    ),
                )
            )

        return BuildingAssemblyResponse(
            building_id=building_id,
            reference_floor_id=reference_floor_id,
            floors=assembly_floors,
        )

    @staticmethod
    def _stored_points(raw_points) -> list[ControlPoint]:  # type: ignore[no-untyped-def]
        """Преобразовать сохранённый список точек в модели ControlPoint.

        Битые записи пропускаются, чтобы старые данные не ломали чтение сборки.
        """
        out: list[ControlPoint] = []
        for p in raw_points or []:
            if not isinstance(p, dict):
                continue
            try:
                out.append(
                    ControlPoint(id=str(p["id"]), x=float(p["x"]), y=float(p["y"]))
                )
            except (KeyError, ValueError, TypeError):
                continue
        return out

    @staticmethod
    def _points_by_id(raw_points) -> dict[str, tuple[float, float]]:  # type: ignore[no-untyped-def]
        """Проиндексировать сохранённый список точек по id."""
        out: dict[str, tuple[float, float]] = {}
        for p in raw_points or []:
            if isinstance(p, dict) and p.get("id") is not None:
                out[str(p["id"])] = (float(p["x"]), float(p["y"]))
        return out

    @staticmethod
    def _similarity_to_dict(
        comp: Optional[SimilarityT],
        floor,  # type: ignore[no-untyped-def]
        solves: list[_PairSolve],
    ) -> Optional[dict]:
        """Собрать JSON building_transform для записи этажа.

        None очищает устаревшее преобразование. scale/rotation_rad/tx/ty берутся
        из собранного преобразования цепочки, residual_rms_px и n_points из записи
        пары самого этажа.
        """
        if comp is None:
            return None
        solve = next((s for s in solves if s.floor_id == floor.id), None)
        residual = solve.residual_rms_px if solve else 0.0
        n_points = solve.n_points if solve else 0
        return {
            "scale": comp.scale,
            "rotation_rad": comp.rotation_rad,
            "tx": comp.tx,
            "ty": comp.ty,
            "residual_rms_px": residual,
            "n_points": n_points,
        }

    @staticmethod
    def _build_stitch_transform(
        comp: Optional[SimilarityT],
        solve: _PairSolve,
    ) -> Optional[StitchTransform]:
        """Собрать StitchTransform для ответа из собранного преобразования."""
        if comp is None:
            return None
        return StitchTransform(
            scale=comp.scale,
            rotation_rad=comp.rotation_rad,
            tx=comp.tx,
            ty=comp.ty,
            residual_rms_px=solve.residual_rms_px,
            n_points=solve.n_points,
        )

    @staticmethod
    def _residual_in_metres(solve: _PairSolve) -> Optional[float]:
        """Перевести пиксельную невязку пары в метры через ppm этажа."""
        if solve.status == "reference":
            return 0.0
        if solve.status != "ok":
            return None
        ppm = solve.pixels_per_meter
        if ppm is None or not math.isfinite(ppm) or ppm <= 0:
            return None
        return solve.residual_rms_px / ppm

    @staticmethod
    def _pair_status(
        floor,  # type: ignore[no-untyped-def]
        is_reference: bool,
        has_mask: bool,
    ) -> str:
        """Определить pair_status этажа для чтения сборки."""
        if is_reference:
            return "reference"
        if not has_mask:
            return "no_mask"
        if floor.building_transform:
            return "ok"
        upper = floor.stitch_points or []
        lower = floor.stitch_ref_points or []
        paired = len({str(p["id"]) for p in upper if isinstance(p, dict)} &
                     {str(p["id"]) for p in lower if isinstance(p, dict)})
        if paired < MIN_CONTROL_POINTS:
            return "needs_points"
        return "unsolved"

    def _floor_mask_dims(self, floor) -> Optional[tuple[int, int]]:  # type: ignore[no-untyped-def]
        """Размеры маски этажа (W, H), либо None если маски нет или файл отсутствует.

        Нечитаемый файл это ImageProcessingError.
        """
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

    @staticmethod
    def _floor_mask_url(floor) -> Optional[str]:  # type: ignore[no-untyped-def]
        """URL сохранённой маски этажа, либо None."""
        mask_file = getattr(floor, "mask_file", None)
        if getattr(floor, "mask_file_id", None) and mask_file is not None:
            return mask_file.url
        return None
