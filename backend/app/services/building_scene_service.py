"""Сборка данных для 3D-просмотра здания этажами (только чтение).

Для каждого этажа отдаёт URL его GLB и позицию в мировой системе координат здания
(система опорного, нижнего этажа). Опорный этаж всегда стоит в начале координат.
Невыровненные этажи получают placement=None: в сцене они пропускаются.

building_transform переводит пиксели маски этажа в пиксели маски опорного этажа,
elevation_m = (number - min_number) * FLOOR_HEIGHT.
"""

import logging
from typing import Optional

import cv2

from app.core.exceptions import (
    BuildingNotFoundError,
    FileStorageError,
    ImageProcessingError,
)
from app.core.floor_stitching_constants import FLOOR_HEIGHT, INTER_FLOOR_GAP_M
from app.db.repositories.building_repo import BuildingRepository
from app.db.repositories.floor_repo import FloorRepository
from app.models.building_scene import (
    BuildingScene3DResponse,
    ScenePlacement,
    SceneFloor,
)
from app.processing.building_stack import Placement3D, floor_placement
from app.services.file_storage import FileStorage

logger = logging.getLogger(__name__)


class BuildingSceneService:
    """Готовит данные 3D-сцены здания этажами."""

    def __init__(
        self,
        building_repo: BuildingRepository,
        floor_repo: FloorRepository,
        storage: FileStorage,
    ) -> None:
        self._building_repo = building_repo
        self._floor_repo = floor_repo
        self._storage = storage

    async def get_scene_3d(self, building_id: int) -> BuildingScene3DResponse:
        """Собрать 3D-сцену здания.

        Этажи без меша или без позиции тоже попадают в ответ: просмотрщик их
        пропускает, а интерфейс показывает причину.
        """
        logger.debug("get_scene_3d: building_id=%d", building_id)
        building = await self._building_repo.get_by_id(building_id)
        if building is None:
            raise BuildingNotFoundError(building_id)

        floors = await self._floor_repo.list_by_building(building_id)
        if not floors:
            return BuildingScene3DResponse(
                building_id=building_id,
                reference_floor_id=None,
                floor_height_m=FLOOR_HEIGHT,
                floors=[],
            )

        # Список отсортирован по number, floors[0] это опорный этаж.
        min_number = floors[0].number
        reference_floor_id = floors[0].id
        ppm_ref = floors[0].pixels_per_meter
        ref_dims = self._floor_mask_dims(floors[0])
        mask_h_ref = ref_dims[1] if ref_dims else None

        scene_floors: list[SceneFloor] = []
        for floor in floors:
            # Зазор отодвигает плиту верхнего этажа от стен нижнего: без него при
            # одном лишь FLOOR_HEIGHT они пересекаются.
            elevation = (floor.number - min_number) * (FLOOR_HEIGHT + INTER_FLOOR_GAP_M)
            has_mesh = floor.mesh_file_glb is not None
            mesh_url = (
                self._storage.uploads_url_versioned(floor.mesh_file_glb)
                if has_mesh
                else None
            )
            placement = self._placement_for(
                floor,
                is_reference=(floor.id == reference_floor_id),
                ppm_ref=ppm_ref,
                mask_h_ref=mask_h_ref,
                elevation=elevation,
            )
            scene_floors.append(
                SceneFloor(
                    floor_id=floor.id,
                    number=floor.number,
                    elevation_m=elevation,
                    has_mesh=has_mesh,
                    mesh_url=mesh_url,
                    placement=placement,
                )
            )

        return BuildingScene3DResponse(
            building_id=building_id,
            reference_floor_id=reference_floor_id,
            floor_height_m=FLOOR_HEIGHT,
            floors=scene_floors,
        )

    def _placement_for(
        self,
        floor,  # type: ignore[no-untyped-def]
        is_reference: bool,
        ppm_ref: Optional[float],
        mask_h_ref: Optional[int],
        elevation: float,
    ) -> Optional[ScenePlacement]:
        """Вычислить позицию этажа в сцене, либо None.

        Опорному этажу всегда соответствует начало координат. Остальным нужны ppm и
        высота маски этого и опорного этажа; если чего-то нет или этаж не выровнен,
        возвращается None.
        """
        if is_reference:
            return ScenePlacement(
                scale=1.0, rotation_y_rad=0.0, tx=0.0, ty=0.0, tz=0.0
            )

        ppm_self = floor.pixels_per_meter
        dims = self._floor_mask_dims(floor)
        mask_h_self = dims[1] if dims else None
        if (
            ppm_self is None
            or ppm_ref is None
            or mask_h_self is None
            or mask_h_ref is None
        ):
            return None

        placement = floor_placement(
            floor.building_transform,
            ppm_self=ppm_self,
            ppm_ref=ppm_ref,
            mask_h_self=mask_h_self,
            mask_h_ref=mask_h_ref,
            elevation_m=elevation,
        )
        return self._to_placement(placement)

    @staticmethod
    def _to_placement(p: Optional[Placement3D]) -> Optional[ScenePlacement]:
        """Преобразовать Placement3D в модель ответа ScenePlacement."""
        if p is None:
            return None
        return ScenePlacement(
            scale=p.scale,
            rotation_y_rad=p.rotation_y_rad,
            tx=p.tx,
            ty=p.ty,
            tz=p.tz,
        )

    # IO seam (patched in service tests — Cyrillic-tmp caveat)

    def _floor_mask_dims(self, floor) -> Optional[tuple[int, int]]:  # type: ignore[no-untyped-def]
        """Return the floor's wall-mask pixel dims ``(W, H)``, or ``None``.

        Reads the persisted ``Floor.mask_file`` (``mask_file_id``) from storage. ``None``
        when the floor has no mask or the file is missing on disk (both EXPECTED — the
        floor just cannot be placed yet). An UNDECODABLE file is an UNEXPECTED
        ``ImageProcessingError``. This is the single IO seam service tests patch (no real
        image round-trip — Cyrillic-tmp caveat). Mirrors ``BuildingAssemblyService``.

        Raises:
            ImageProcessingError: the mask file exists but cannot be decoded.
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
