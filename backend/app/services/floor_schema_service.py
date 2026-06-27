"""
FloorSchemaService — orchestrator for the floor schema CV pipeline.

Responsibilities:
- upload_schema: set floor.schema_image_id
- update_crop: set floor.schema_crop_bbox
- extract_walls: call processing/* → store normalised wall_polygons
- update_walls: manual save after user correction

All DB access goes through repositories.
All CV work stays inside processing/ (pure functions).
Coordinate normalisation happens HERE (in service layer), not inside processing/.
"""

import logging
import math
import os

import cv2

from app.core.exceptions import FloorNotFoundError, FloorSchemaError, ImageProcessingError
from app.db.repositories.floor_repo import FloorRepository
from app.models.floors import CropBboxModel

# Reuse existing pure CV functions (processing/ remains pure — no DB/HTTP)
from app.processing.preprocessor import preprocess_image
from app.processing.vectorizer import find_contours as vectorizer_find_contours

logger = logging.getLogger(__name__)

# Min contour perimeter as fraction of normalised diagonal (√2 ≈ 1.414)
_MIN_PERIMETER_RATIO = 0.01
_NORMALISED_DIAGONAL = math.sqrt(2.0)
_MIN_PERIMETER = _MIN_PERIMETER_RATIO * _NORMALISED_DIAGONAL


class FloorSchemaService:
    """Orchestrates upload + CV pipeline for floor schema images."""

    def __init__(
        self,
        floor_repo: FloorRepository,
        upload_dir: str,
    ) -> None:
        self._floor_repo = floor_repo
        self._upload_dir = upload_dir

    # Schema image

    async def upload_schema(self, floor_id: int, image_id: str) -> None:
        """Assign an already-uploaded file as the floor schema image.

        When the image actually CHANGES (a different карта отсеков is uploaded),
        the previously derived data — crop, wall_polygons and the edited mask —
        describe the OLD image and are no longer valid, so they are cleared. This
        keeps a re-uploaded map from inheriting the previous map's walls/mask.
        Re-saving the SAME image (e.g. the crop-commit path) preserves everything.

        Raises:
            FloorNotFoundError: if floor absent.
            FloorSchemaError: if image_id not found in storage.
        """
        logger.info("upload_schema: floor_id=%d, image_id=%s", floor_id, image_id)
        floor = await self._floor_repo.get_by_id(floor_id)
        if not floor:
            raise FloorNotFoundError(floor_id)

        # Validate the file exists on disk
        image_path = self._find_image(image_id)
        if not image_path:
            raise FloorSchemaError(f"Image file '{image_id}' not found in storage")

        image_changed = floor.schema_image_id != image_id
        await self._floor_repo.update_schema(
            floor_id=floor_id,
            schema_image_id=image_id,
            # Drop the old crop on a new image; keep it when re-saving the same one.
            schema_crop_bbox=None if image_changed else floor.schema_crop_bbox,
        )
        if image_changed:
            await self._floor_repo.update_wall_polygons(floor_id, [])
            await self._floor_repo.update_mask(floor_id, None)
            logger.info(
                "upload_schema: image changed → cleared crop/walls/mask (floor_id=%d)",
                floor_id,
            )
        logger.debug("upload_schema done: floor_id=%d, image_id=%s", floor_id, image_id)

    async def reset_schema(self, floor_id: int) -> None:
        """Fully clear the floor schema so a brand-new карта отсеков can be loaded.

        Nulls schema_image_id, schema_crop_bbox, wall_polygons and mask_file_id.
        Sections are removed separately by the caller (sections replace-all), since
        they live in their own table / repository.

        Raises FloorNotFoundError if floor absent.
        """
        logger.info("reset_schema: floor_id=%d", floor_id)
        floor = await self._floor_repo.get_by_id(floor_id)
        if not floor:
            raise FloorNotFoundError(floor_id)

        await self._floor_repo.update_schema(
            floor_id=floor_id,
            schema_image_id=None,
            schema_crop_bbox=None,
        )
        await self._floor_repo.update_wall_polygons(floor_id, [])
        await self._floor_repo.update_mask(floor_id, None)
        logger.debug("reset_schema done: floor_id=%d", floor_id)

    # Crop bbox

    async def update_crop(self, floor_id: int, bbox: CropBboxModel) -> None:
        """Persist crop/rotation parameters for the floor schema.

        Raises FloorNotFoundError if floor absent.
        """
        logger.info("update_crop: floor_id=%d, bbox=%s", floor_id, bbox)
        floor = await self._floor_repo.get_by_id(floor_id)
        if not floor:
            raise FloorNotFoundError(floor_id)

        await self._floor_repo.update_schema(
            floor_id=floor_id,
            schema_image_id=floor.schema_image_id,
            schema_crop_bbox=bbox.model_dump(),
        )

    # Wall extraction

    async def extract_walls(self, floor_id: int) -> list[list[list[float]]]:
        """Run CV pipeline on the floor schema and store normalised wall_polygons.

        Algorithm:
            1. Load image from storage
            2. Apply crop+rotation via preprocess_image (existing pure function)
            3. Find contours on the binary mask
            4. Normalise contour points to [0,1] relative to cropped+rotated image
            5. Filter tiny artefacts (< 1% of diagonal)
            6. Save polygons to Floor.wall_polygons
            7. Return polygons

        Processing/ functions used (unchanged, remain pure):
            - preprocess_image (processing/preprocessor.py)
            - vectorizer.find_contours (processing/vectorizer.py)

        Coordinate normalisation is done HERE, not inside processing/.

        Raises:
            FloorNotFoundError: floor absent.
            FloorSchemaError: schema_image_id not set, or file missing.
            ImageProcessingError: cv2.imread returned None (corrupt file).
        """
        logger.info("extract_walls: floor_id=%d", floor_id)
        floor = await self._floor_repo.get_by_id(floor_id)
        if not floor:
            raise FloorNotFoundError(floor_id)

        if not floor.schema_image_id:
            raise FloorSchemaError("Floor schema image not uploaded")

        # 1. Load image from storage
        image_path = self._find_image(floor.schema_image_id)
        if not image_path:
            raise FloorSchemaError("Schema image file missing")

        image = cv2.imread(image_path)
        if image is None:
            raise ImageProcessingError(
                "extract_walls", "Failed to read image (corrupt file?)"
            )

        # 2. Preprocess: apply crop+rotation → binary mask (walls = 255, bg = 0)
        crop_dict = floor.schema_crop_bbox  # already a dict or None
        rotation = 0
        if crop_dict:
            rotation = crop_dict.get("rotation", 0)
            # preprocess_image handles crop internally via the `crop` arg
        binary = preprocess_image(image, crop=crop_dict, rotation=rotation)

        # 3. The binary mask shape gives us the cropped+rotated dimensions
        h, w = binary.shape[:2]
        if w == 0 or h == 0:
            raise ImageProcessingError("extract_walls", "Invalid crop region")

        # 4. Find contours on the binary mask (existing pure function from vectorizer.py)
        raw_contours = vectorizer_find_contours(binary)

        # 5. Normalise coordinates to [0,1] relative to cropped image
        #    AND filter tiny artefacts by perimeter
        polygons: list[list[list[float]]] = []
        for contour in raw_contours:
            # contour shape: (N, 1, 2)
            pts = contour.reshape(-1, 2)
            normalised = [[float(pt[0]) / w, float(pt[1]) / h] for pt in pts]

            # Compute perimeter in normalised space
            perim = _compute_perimeter(normalised)
            if perim >= _MIN_PERIMETER:
                polygons.append(normalised)

        logger.info(
            "extract_walls: floor_id=%d → %d polygons found", floor_id, len(polygons)
        )

        # 6. Persist
        await self._floor_repo.update_wall_polygons(floor_id, polygons)
        return polygons

    # Manual wall update

    async def update_walls(
        self, floor_id: int, polygons: list[list[list[float]]]
    ) -> None:
        """Persist manually edited wall polygons (post-user correction).

        Raises FloorNotFoundError if floor absent.
        """
        logger.info(
            "update_walls: floor_id=%d, polygons=%d", floor_id, len(polygons)
        )
        floor = await self._floor_repo.get_by_id(floor_id)
        if not floor:
            raise FloorNotFoundError(floor_id)

        await self._floor_repo.update_wall_polygons(floor_id, polygons)

    # Persisted wall mask

    async def update_mask(self, floor_id: int, mask_file_id: str) -> None:
        """Link an already-uploaded mask PNG as the floor's persisted wall mask.

        The client uploads the file via POST /upload/user-mask/ before this call,
        so no disk validation is done here (mirrors update_walls — keep light).

        Raises FloorNotFoundError if floor absent.
        """
        logger.info(
            "update_mask: floor_id=%d, mask_file_id=%s", floor_id, mask_file_id
        )
        floor = await self._floor_repo.get_by_id(floor_id)
        if not floor:
            raise FloorNotFoundError(floor_id)

        await self._floor_repo.update_mask(floor_id, mask_file_id)

    # Private helpers

    def _find_image(self, image_id: str) -> str | None:
        """Search common upload subfolders for a file with the given ID prefix."""
        subfolders = ["plans", "schemas", "masks", ""]
        import glob

        for subfolder in subfolders:
            if subfolder:
                pattern = os.path.join(self._upload_dir, subfolder, f"{image_id}.*")
            else:
                pattern = os.path.join(self._upload_dir, f"{image_id}.*")
            matches = glob.glob(pattern)
            if matches:
                return matches[0]
        return None


def _compute_perimeter(points: list[list[float]]) -> float:
    """Compute closed-polygon perimeter in normalised [0,1] space."""
    if len(points) < 2:
        return 0.0
    total = 0.0
    for i in range(len(points)):
        x0, y0 = points[i]
        x1, y1 = points[(i + 1) % len(points)]
        total += math.sqrt((x1 - x0) ** 2 + (y1 - y0) ** 2)
    return total
