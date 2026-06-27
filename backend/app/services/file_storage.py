"""
File storage abstraction for managing uploads and model exports.
"""
import glob
import json
import logging
import os
import re
import shutil
import uuid
from typing import List, Optional

import cv2
import numpy as np

from app.core.exceptions import FileStorageError, ImageProcessingError
from app.models.domain import TextBlock

logger = logging.getLogger(__name__)

# Strict handle for a floor build-preview GLB, e.g. "floor-3-preview-7f3a9c1d".
# ``\Z`` (NOT ``$``) anchors the END OF STRING: ``$`` also matches just before a
# trailing ``\n``, which would let "floor-3-preview-deadbeef\n" slip into
# os.path.join (path traversal / smuggled newline). The floor-id and 8-hex token
# are captured so the service can assert the id segment equals the path arg.
_PREVIEW_ID_RE = re.compile(r"floor-(\d+)-preview-([0-9a-f]{8})\Z")


class FileStorage:
    """Handles all file I/O operations for uploads and exports."""

    def __init__(self, upload_dir: str) -> None:
        """
        Initialize file storage.

        Args:
            upload_dir: Root directory for uploads and exports
        """
        self._upload_dir = upload_dir
        self._models_dir = os.path.join(upload_dir, "models")
        os.makedirs(self._models_dir, exist_ok=True)
        logger.debug("FileStorage initialized: upload_dir=%s", upload_dir)

    @staticmethod
    def uploads_url(rel_path: str) -> str:
        """Map a storage-relative path to its static URL.

        E.g. ``"models/floor_3.glb"`` → ``"/api/v1/uploads/models/floor_3.glb"``. Mirrors
        the ``/api/v1/uploads/...`` convention used by ``save_floor_preview_mesh`` /
        ``promote_floor_preview``. Normalises Windows separators and strips any leading
        slash so the result always has single forward slashes.

        Args:
            rel_path: a path relative to the uploads root (e.g. ``Floor.mesh_file_glb``).

        Returns:
            The static URL ``/api/v1/uploads/<rel_path>``.
        """
        rel = rel_path.replace("\\", "/").lstrip("/")
        return f"/api/v1/uploads/{rel}"

    def uploads_url_versioned(self, rel_path: str) -> str:
        """``uploads_url`` + a ``?v=<mtime>`` cache-buster.

        A rebuilt file at the SAME path (e.g. ``models/floor_3.glb`` after a re-confirm)
        otherwise gets served stale from the browser / ``useGLTF`` cache. Appending the
        file's mtime makes the URL change whenever the bytes change. Falls back to the
        plain URL if the file cannot be stat'd.

        Args:
            rel_path: a path relative to the uploads root.

        Returns:
            ``/api/v1/uploads/<rel>?v=<mtime>`` (or the plain URL on stat failure).
        """
        url = self.uploads_url(rel_path)
        rel = rel_path.replace("\\", "/").lstrip("/")
        try:
            mtime = int(os.path.getmtime(os.path.join(self._upload_dir, rel)))
        except OSError:
            return url
        return f"{url}?v={mtime}"

    def find_file(self, file_id: str, subfolder: str) -> str:
        """
        Find file by ID in subfolder (any extension).

        Args:
            file_id: File identifier
            subfolder: Subfolder name (e.g., "masks", "plans")

        Returns:
            Full path to file

        Raises:
            FileStorageError: If file not found
        """
        pattern = os.path.join(self._upload_dir, subfolder, f"{file_id}.*")
        files = glob.glob(pattern)
        if not files:
            raise FileStorageError(file_id, pattern)
        logger.debug("Found file: %s", files[0])
        return files[0]

    async def load_mask(self, mask_file_id: str) -> np.ndarray:
        """
        Load mask image as grayscale array.

        Args:
            mask_file_id: Mask file identifier

        Returns:
            Grayscale image array (np.uint8)

        Raises:
            FileStorageError: If file not found
            ImageProcessingError: If image cannot be loaded
        """
        mask_path = self.find_file(mask_file_id, "masks")
        mask_array = cv2.imread(mask_path, cv2.IMREAD_GRAYSCALE)
        if mask_array is None:
            msg = f"Failed to load mask: {mask_path}"
            raise ImageProcessingError("cv2.imread", msg)
        logger.debug("Loaded mask: %s, shape=%s", mask_path, mask_array.shape)
        return mask_array

    async def load_text_blocks(
        self, mask_file_id: str
    ) -> Optional[List[TextBlock]]:
        """
        Load text blocks from JSON file if exists.

        Args:
            mask_file_id: Mask file identifier

        Returns:
            List of TextBlock objects or None if file doesn't exist

        Raises:
            Exception: If JSON is malformed
        """
        text_json_path = os.path.join(
            self._upload_dir, "masks", f"{mask_file_id}_text.json"
        )
        if not os.path.exists(text_json_path):
            logger.debug("Text blocks file not found: %s", text_json_path)
            return None

        try:
            with open(text_json_path, "r", encoding="utf-8") as f:
                text_data = json.load(f)
            text_blocks = [TextBlock(**tb) for tb in text_data]
            logger.info(
                "Loaded %d text blocks from %s",
                len(text_blocks),
                text_json_path,
            )
            return text_blocks
        except Exception as e:
            logger.warning("Failed to load text blocks: %s", e)
            return None

    async def save_mesh_files(
        self, reconstruction_id: int, mesh
    ) -> tuple[str, str]:
        """
        Export mesh to OBJ and GLB files.

        Args:
            reconstruction_id: Reconstruction ID
            mesh: Trimesh mesh object to export

        Returns:
            Tuple of (obj_path, glb_path)
        """
        obj_path = os.path.join(
            self._models_dir, f"reconstruction_{reconstruction_id}.obj"
        )
        glb_path = os.path.join(
            self._models_dir, f"reconstruction_{reconstruction_id}.glb"
        )

        mesh.export(obj_path)
        mesh.export(glb_path)
        logger.debug("Mesh exported: obj=%s, glb=%s", obj_path, glb_path)
        return obj_path, glb_path

    # Floor build-preview GLBs (floor-stitching)
    # Preview→confirm is stateless/disk-based: there is no DB registry, so the
    # opaque ``glb_file_id`` IS the file locator and MUST be validated strictly
    # on the way back in (path-traversal / cross-floor safety — see).

    async def save_floor_preview_mesh(
        self, floor_id: int, mesh
    ) -> tuple[str, str]:
        """Export a stitched-floor mesh as a NON-persisted preview GLB.

        Writes ``models/floor_{floor_id}_preview_{token}.glb`` where ``token`` is
        a random 8-hex handle. Mirrors ``save_mesh_files`` but emits a single GLB
        and an opaque ``glb_file_id`` handle (no DB row). The export is ATOMIC:
        it writes ``<path>.tmp`` then ``os.replace`` (atomic on the same FS), so a
        concurrent reader never observes a half-written GLB. ``floors.mesh_file_glb``
        is NOT touched here (— confirm promotes a preview, never build).

        Args:
            floor_id: owning floor id (embedded in the handle for cross-floor
                validation at confirm time).
            mesh: trimesh mesh to export.

        Returns:
            ``(glb_file_id, glb_url)`` — the handle ``floor-{id}-preview-{token}``
            and its static URL under ``/api/v1/uploads/models/``.
        """
        token = uuid.uuid4().hex[:8]
        glb_file_id = f"floor-{floor_id}-preview-{token}"
        filename = f"floor_{floor_id}_preview_{token}.glb"
        glb_path = os.path.join(self._models_dir, filename)

        tmp_path = glb_path + ".tmp"
        # Explicit file_type: the ".tmp" suffix hides the ".glb" extension, so
        # trimesh cannot infer the exporter from the path.
        mesh.export(tmp_path, file_type="glb")
        os.replace(tmp_path, glb_path)

        glb_url = f"/api/v1/uploads/models/{filename}"
        logger.info("Floor preview GLB exported: %s", glb_path)
        return glb_file_id, glb_url

    def floor_preview_path(self, floor_id: int, glb_file_id: str) -> str:
        """Resolve + STRICTLY validate a preview handle to an on-disk path.

        Security boundary: ``glb_file_id`` is an opaque, client-supplied string
        used to locate a file, so it is validated with ``re.fullmatch`` against
        ``floor-(\\d+)-preview-([0-9a-f]{8})`` anchored with ``\\Z`` (NOT ``$`` —
        ``$`` matches before a trailing ``\\n``). The captured floor-id segment
        MUST equal the ``floor_id`` path arg, otherwise a caller could confirm
        ``floor-7-preview-…`` against ``/floors/3/confirm-mesh`` and promote another
        floor's preview. The token is constrained to 8 lowercase hex chars, so the
        composed filename can contain no path separators / ``..`` / NUL.

        Args:
            floor_id: floor the handle must belong to.
            glb_file_id: opaque preview handle to validate.

        Returns:
            Absolute path ``<models>/floor_{floor_id}_preview_{token}.glb``.

        Raises:
            FileStorageError: handle malformed or belongs to a different floor.
        """
        match = _PREVIEW_ID_RE.fullmatch(glb_file_id)
        if match is None:
            raise FileStorageError(
                glb_file_id, "invalid floor preview handle"
            )
        handle_floor_id = int(match.group(1))
        token = match.group(2)
        if handle_floor_id != floor_id:
            raise FileStorageError(
                glb_file_id,
                f"preview handle floor {handle_floor_id} != floor {floor_id}",
            )
        filename = f"floor_{floor_id}_preview_{token}.glb"
        return os.path.join(self._models_dir, filename)

    async def promote_floor_preview(
        self, floor_id: int, glb_file_id: str
    ) -> tuple[str, str]:
        """Promote a validated preview GLB to the persisted floor model GLB.

        Resolves + validates ``glb_file_id`` via ``floor_preview_path`` (cross-floor
        / traversal safe), asserts the preview exists, then ATOMICALLY copies it to
        ``models/floor_{floor_id}.glb`` (copy → ``<final>.tmp`` → ``os.replace``) so
        a reader never sees a partially-copied final GLB.

        Args:
            floor_id: floor to promote into.
            glb_file_id: preview handle from a prior ``save_floor_preview_mesh``.

        Returns:
            ``(rel_path, url)`` — the relative path ``models/floor_{id}.glb`` to
            persist on ``floors.mesh_file_glb`` and its static URL.

        Raises:
            FileStorageError: handle invalid / cross-floor, or preview file missing
                (the service maps the missing-preview case to PreviewNotFoundError).
        """
        preview_path = self.floor_preview_path(floor_id, glb_file_id)
        if not os.path.isfile(preview_path):
            raise FileStorageError(glb_file_id, preview_path)

        filename = f"floor_{floor_id}.glb"
        final_path = os.path.join(self._models_dir, filename)
        tmp_path = final_path + ".tmp"
        shutil.copyfile(preview_path, tmp_path)
        os.replace(tmp_path, final_path)

        rel_path = f"models/{filename}"
        url = f"/api/v1/uploads/models/{filename}"
        logger.info("Floor preview promoted: %s -> %s", preview_path, final_path)
        return rel_path, url

    async def save_mesh(
        self, reconstruction_id: int, obj_path: str, glb_path: str
    ) -> None:
        """
        Ensure mesh export paths are in models directory.

        Args:
            reconstruction_id: Reconstruction ID
            obj_path: OBJ file path
            glb_path: GLB file path

        Note:
            Mesh export is handled by mesh.export() in the service.
            This method validates paths are in the correct directory.
        """
        for path in [obj_path, glb_path]:
            if not path.startswith(self._models_dir):
                logger.warning("Mesh path outside models dir: %s", path)
        logger.info("Mesh paths validated: obj=%s, glb=%s", obj_path, glb_path)

    async def save_uploaded_file(
        self,
        file_content: bytes,
        filename: str,
        subfolder: str = "",
    ) -> str:
        """
        Save uploaded file to storage.

        Args:
            file_content: File content as bytes
            filename: Original filename (for extension)
            subfolder: Subdirectory within upload_dir

        Returns:
            Generated file_id (UUID)

        Raises:
            FileStorageError: If save fails
        """
        file_id = str(uuid.uuid4())
        ext = filename.split(".")[-1].lower() if filename else "jpg"

        upload_dir = os.path.join(self._upload_dir, subfolder)
        os.makedirs(upload_dir, exist_ok=True)

        file_path = os.path.join(upload_dir, f"{file_id}.{ext}")

        try:
            with open(file_path, "wb") as f:
                f.write(file_content)
            logger.info("File saved: %s", file_path)
            return file_id
        except Exception as e:
            logger.error("Failed to save file: %s", e, exc_info=True)
            raise FileStorageError(file_id, f"Failed to save: {e}")
