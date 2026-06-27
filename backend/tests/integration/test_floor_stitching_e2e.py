"""End-to-end smoke test for the floor-stitching pipeline.

Seeds a fully synthetic building → floor → 2 sections (generated wall-mask PNGs +
a blank master schema), places control points so the solve is EXACT, then runs the
REAL ``FloorAssemblyService``: solve → build → confirm, and asserts a non-empty
floor GLB on disk. No mocks — real SQLite (temp file), real PNGs, real cv2 +
trimesh. Covers AC1–AC7 working end to end.
"""

import json
import os
import shutil
import tempfile
import uuid

import cv2
import numpy as np
import pytest
import pytest_asyncio
import trimesh
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.database import Base
import app.db.base  # noqa: F401 — registers every ORM model with Base.metadata
from app.db.models.building import Building, Floor
from app.db.models.reconstruction import Reconstruction, UploadedFile
from app.db.models.section import Section
from app.db.repositories.floor_connector_repo import FloorConnectorRepository
from app.db.repositories.floor_repo import FloorRepository
from app.db.repositories.reconstruction_repo import ReconstructionRepository
from app.db.repositories.section_repo import SectionRepository
from app.services.file_storage import FileStorage
from app.services.floor_assembly_service import FloorAssemblyService

# Synthetic geometry (chosen so the solve is exact)

SECTION_W = SECTION_H = 200
MASTER_W = MASTER_H = 600
PPM_SECTION = 50.0

# Section-local control points (normalised over the 200×200 section): 3 well-spread,
# non-collinear corners → baseline well above the degeneracy threshold.
SECTION_CPS = [
    {"id": "cp-1", "x": 0.10, "y": 0.10},  # section px (20, 20)
    {"id": "cp-2", "x": 0.90, "y": 0.10},  # section px (180, 20)
    {"id": "cp-3", "x": 0.50, "y": 0.90},  # section px (100, 180)
]

# Each section maps into the master by an EXACT uniform similarity
# master_px = scale·section_px + off, so the registration residual is ~0 and both
# sections imply the SAME ppm (50 × 1.5 = 75) — no ppm-spread warning.
SECTION_PLACEMENTS = [
    {"number": 1, "scale": 1.5, "off": (50.0, 50.0)},
    {"number": 2, "scale": 1.5, "off": (300.0, 300.0)},
]


def _wall_mask() -> np.ndarray:
    """200×200 grayscale mask with a ~14%-white rectangular wall ring (walls=255)."""
    mask = np.zeros((SECTION_H, SECTION_W), np.uint8)
    cv2.rectangle(mask, (30, 30), (170, 170), 255, thickness=10)
    return mask


def _master_control_points(scale: float, off: tuple[float, float]) -> list[dict]:
    """Master CPs (normalised over the 600×600 master) = exact image of SECTION_CPS."""
    pts: list[dict] = []
    for cp in SECTION_CPS:
        sx, sy = cp["x"] * SECTION_W, cp["y"] * SECTION_H
        mx, my = scale * sx + off[0], scale * sy + off[1]
        pts.append({"point_id": cp["id"], "x": mx / MASTER_W, "y": my / MASTER_H})
    return pts


# Fixtures: temp file DB + temp upload dir + real FileStorage


@pytest.fixture
def upload_dir() -> str:
    # OpenCV's imread/imwrite use the Windows ANSI API and FAIL on non-ASCII paths;
    # pytest's tmp_path lives under the (Cyrillic) home dir, so use an ASCII temp
    # dir under the repo instead — both the seeding cv2.imwrite and the service's
    # cv2.imread need an ASCII path (production UPLOAD_DIR is ASCII too).
    backend_dir = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    work = tempfile.mkdtemp(prefix="e2e_", dir=backend_dir)
    for sub in ("masks", "schemas", "plans", "models"):
        os.makedirs(os.path.join(work, sub), exist_ok=True)
    try:
        yield work
    finally:
        shutil.rmtree(work, ignore_errors=True)


@pytest_asyncio.fixture
async def session(upload_dir) -> AsyncSession:
    # A FILE-based SQLite DB (not :memory:) under the ASCII workdir so create_all
    # and the session share one database across the driver's connection pool.
    db_path = os.path.join(upload_dir, "e2e.db").replace(os.sep, "/")
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


async def _seed_floor(session: AsyncSession, upload_dir: str) -> int:
    """Seed building → floor (+schema PNG) → 2 bound sections (+mask PNGs). Returns floor id."""
    # Master schema: only its DIMENSIONS are read (for the master-pixel canvas), so
    # a blank 600×600 image suffices.
    schema_id = str(uuid.uuid4())
    cv2.imwrite(
        os.path.join(upload_dir, "schemas", f"{schema_id}.png"),
        np.zeros((MASTER_H, MASTER_W, 3), np.uint8),
    )
    session.add(
        UploadedFile(
            id=schema_id,
            filename="schema.png",
            file_path=f"schemas/{schema_id}.png",
            url=f"/api/v1/uploads/schemas/{schema_id}.png",
            file_type=3,
        )
    )
    building = Building(code="E2E", name="E2E Building")
    session.add(building)
    await session.flush()

    floor = Floor(
        building_id=building.id,
        number=1,
        schema_image_id=schema_id,
        schema_crop_bbox=None,  # full image → master dims = 600×600
    )
    session.add(floor)
    await session.flush()

    for place in SECTION_PLACEMENTS:
        plan_id, mask_id = str(uuid.uuid4()), str(uuid.uuid4())
        cv2.imwrite(os.path.join(upload_dir, "masks", f"{mask_id}.png"), _wall_mask())
        session.add(
            UploadedFile(
                id=plan_id, filename="plan.png", file_path=f"plans/{plan_id}.png",
                url=f"/api/v1/uploads/plans/{plan_id}.png", file_type=1,
            )
        )
        session.add(
            UploadedFile(
                id=mask_id, filename="mask.png", file_path=f"masks/{mask_id}.png",
                url=f"/api/v1/uploads/masks/{mask_id}.png", file_type=2,
            )
        )
        await session.flush()

        recon = Reconstruction(
            plan_file_id=plan_id,
            mask_file_id=mask_id,
            status=3,
            name=f"Section {place['number']}",
            control_points=SECTION_CPS,
            vectorization_data=json.dumps(
                {
                    "image_size_cropped": [SECTION_W, SECTION_H],
                    "estimated_pixels_per_meter": PPM_SECTION,
                }
            ),
        )
        session.add(recon)
        await session.flush()

        session.add(
            Section(
                floor_id=floor.id,
                number=place["number"],
                section_type=1,
                geometry={"points": [[0.1, 0.1], [0.4, 0.1], [0.4, 0.5], [0.1, 0.5]]},
                reconstruction_id=recon.id,
                control_points=_master_control_points(place["scale"], place["off"]),
            )
        )

    await session.commit()
    return floor.id


def _make_service(session: AsyncSession, storage: FileStorage) -> FloorAssemblyService:
    return FloorAssemblyService(
        floor_repo=FloorRepository(session),
        section_repo=SectionRepository(session),
        reconstruction_repo=ReconstructionRepository(session),
        connector_repo=FloorConnectorRepository(session),
        storage=storage,
    )


# The end-to-end test


@pytest.mark.asyncio
async def test_floor_stitching_e2e_solve_build_confirm_produces_nonempty_glb(
    session, upload_dir
):
    floor_id = await _seed_floor(session, upload_dir)
    storage = FileStorage(upload_dir=upload_dir)
    svc = _make_service(session, storage)

    #solve — every section registers exactly (residual ~0, scale 1.5).
    solve = await svc.solve_transforms(floor_id)
    assert [s.status for s in solve.sections] == ["ok", "ok"]
    assert solve.pixels_per_meter == pytest.approx(75.0, rel=1e-2)  # 50 × 1.5
    for s in solve.sections:
        assert s.transform is not None
        assert s.transform.scale == pytest.approx(1.5, rel=1e-2)
        assert s.transform.residual_rms_px < 1.0
        assert s.warning is None  # exact fit + consistent ppm → no warnings

    # build: preview-only GLB (mesh_file_glb NOT yet set).
    build = await svc.build_floor_mesh(floor_id)
    assert build.persisted is False
    assert build.glb_file_id.startswith(f"floor-{floor_id}-preview-")
    assert sorted(build.included_sections) and len(build.included_sections) == 2
    assert build.excluded_sections == []
    assert build.canvas_size_px == (MASTER_W, MASTER_H)  # k = 1
    floor_mid = await FloorRepository(session).get_by_id(floor_id)
    assert floor_mid.mesh_file_glb is None # build never persists

    # confirm: promote the preview → floors.mesh_file_glb set.
    confirm = await svc.confirm_floor_mesh(floor_id, build.glb_file_id)
    assert confirm.persisted is True
    assert confirm.mesh_file_glb == f"models/floor_{floor_id}.glb"
    floor_done = await FloorRepository(session).get_by_id(floor_id)
    assert floor_done.mesh_file_glb == f"models/floor_{floor_id}.glb"

    # The persisted GLB is a real, non-empty mesh.
    glb_path = os.path.join(upload_dir, "models", f"floor_{floor_id}.glb")
    assert os.path.isfile(glb_path)
    mesh = trimesh.load(glb_path, force="mesh")
    assert len(mesh.vertices) > 0
    assert len(mesh.faces) > 0


@pytest.mark.asyncio
async def test_floor_stitching_e2e_build_before_solve_conflicts(session, upload_dir):
    """Building before solving (no transforms yet) is a clean 409, not a crash."""
    from app.core.exceptions import FloorAssemblyConflictError

    floor_id = await _seed_floor(session, upload_dir)
    svc = _make_service(session, FileStorage(upload_dir=upload_dir))
    with pytest.raises(FloorAssemblyConflictError):
        await svc.build_floor_mesh(floor_id)
