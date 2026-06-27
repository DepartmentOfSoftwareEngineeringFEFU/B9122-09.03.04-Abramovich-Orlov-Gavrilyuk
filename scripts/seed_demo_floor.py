"""Seed a fully synthetic demo floor and run the stitching pipeline end to end.

Builds a synthetic building, floor and 2 sections (generated wall-mask PNGs plus a
blank master schema) in a throwaway SQLite DB (so it needs no migrations and is
reproducible), places control points so the registration is exact, then runs the
real FloorAssemblyService (solve, build, confirm) and verifies a non-empty
floor GLB. The GLB is written into the live ``uploads/models`` dir so it is
servable at ``/api/v1/uploads/models/floor_<id>.glb`` and can be opened in the
3D viewer.

Usage (run from the backend/ directory):
    cd backend
    python ../scripts/seed_demo_floor.py
"""

import argparse
import asyncio
import json
import logging
import os
import sys
import uuid

import cv2
import numpy as np
import trimesh
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# Make sure backend/ is importable when running from scripts/.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.core.config import settings  # noqa: E402
from app.core.database import Base  # noqa: E402
import app.db.base  # noqa: F401,E402
from app.db.models.building import Building, Floor  # noqa: E402
from app.db.models.reconstruction import Reconstruction, UploadedFile  # noqa: E402
from app.db.models.section import Section  # noqa: E402
from app.db.repositories.floor_connector_repo import FloorConnectorRepository  # noqa: E402
from app.db.repositories.floor_repo import FloorRepository  # noqa: E402
from app.db.repositories.reconstruction_repo import ReconstructionRepository  # noqa: E402
from app.db.repositories.section_repo import SectionRepository  # noqa: E402
from app.services.file_storage import FileStorage  # noqa: E402
from app.services.floor_assembly_service import FloorAssemblyService  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("seed_demo_floor")

# Synthetic geometry, chosen so the solve is exact.
SECTION_W = SECTION_H = 200
MASTER_W = MASTER_H = 600
PPM_SECTION = 50.0
DEMO_DB = "seed_demo_floor.db"

SECTION_CPS = [
    {"id": "cp-1", "x": 0.10, "y": 0.10},
    {"id": "cp-2", "x": 0.90, "y": 0.10},
    {"id": "cp-3", "x": 0.50, "y": 0.90},
]
SECTION_PLACEMENTS = [
    {"number": 1, "scale": 1.5, "off": (50.0, 50.0)},
    {"number": 2, "scale": 1.5, "off": (300.0, 300.0)},
]


def _wall_mask() -> np.ndarray:
    mask = np.zeros((SECTION_H, SECTION_W), np.uint8)
    cv2.rectangle(mask, (30, 30), (170, 170), 255, thickness=10)
    return mask


def _master_control_points(scale: float, off) -> list:
    pts = []
    for cp in SECTION_CPS:
        sx, sy = cp["x"] * SECTION_W, cp["y"] * SECTION_H
        mx, my = scale * sx + off[0], scale * sy + off[1]
        pts.append({"point_id": cp["id"], "x": mx / MASTER_W, "y": my / MASTER_H})
    return pts


async def _seed(session: AsyncSession, upload_dir: str, generated: list) -> int:
    """Seed building, floor (with schema PNG) and 2 bound sections (with mask PNGs)."""
    schema_id = str(uuid.uuid4())
    schema_path = os.path.join(upload_dir, "schemas", f"{schema_id}.png")
    cv2.imwrite(schema_path, np.zeros((MASTER_H, MASTER_W, 3), np.uint8))
    generated.append(schema_path)
    session.add(
        UploadedFile(
            id=schema_id, filename="schema.png",
            file_path=f"schemas/{schema_id}.png",
            url=f"/api/v1/uploads/schemas/{schema_id}.png", file_type=3,
        )
    )
    building = Building(code="DMO", name="Demo Building")
    session.add(building)
    await session.flush()
    floor = Floor(building_id=building.id, number=1, schema_image_id=schema_id)
    session.add(floor)
    await session.flush()

    for place in SECTION_PLACEMENTS:
        plan_id, mask_id = str(uuid.uuid4()), str(uuid.uuid4())
        mask_path = os.path.join(upload_dir, "masks", f"{mask_id}.png")
        cv2.imwrite(mask_path, _wall_mask())
        generated.append(mask_path)
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
            plan_file_id=plan_id, mask_file_id=mask_id, status=3,
            name=f"Demo section {place['number']}",
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
                floor_id=floor.id, number=place["number"], section_type=1,
                geometry={"points": [[0.1, 0.1], [0.4, 0.1], [0.4, 0.5], [0.1, 0.5]]},
                reconstruction_id=recon.id,
                control_points=_master_control_points(place["scale"], place["off"]),
            )
        )
    await session.commit()
    return floor.id


async def main() -> None:
    parser = argparse.ArgumentParser(description="Seed a synthetic demo floor + run stitching.")
    parser.add_argument(
        "--keep-intermediate", action="store_true",
        help="Keep the generated section-mask / schema PNGs (default: delete them, keep only the floor GLB).",
    )
    args = parser.parse_args()

    upload_dir = str(settings.UPLOAD_DIR)
    for sub in ("masks", "schemas", "plans", "models"):
        os.makedirs(os.path.join(upload_dir, sub), exist_ok=True)

    # Throwaway DB, recreated each run, no migrations needed.
    db_path = os.path.abspath(DEMO_DB)
    if os.path.exists(db_path):
        os.remove(db_path)
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_path.replace(os.sep, '/')}", echo=False
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    generated: list = []
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with maker() as session:
            floor_id = await _seed(session, upload_dir, generated)
            svc = FloorAssemblyService(
                floor_repo=FloorRepository(session),
                section_repo=SectionRepository(session),
                reconstruction_repo=ReconstructionRepository(session),
                connector_repo=FloorConnectorRepository(session),
                storage=FileStorage(upload_dir=upload_dir),
            )

            solve = await svc.solve_transforms(floor_id)
            statuses = [s.status for s in solve.sections]
            logger.info("solve: statuses=%s ppm=%.2f", statuses, solve.pixels_per_meter or 0)
            assert all(s == "ok" for s in statuses), f"expected all ok, got {statuses}"

            build = await svc.build_floor_mesh(floor_id)
            logger.info(
                "build: glb_file_id=%s included=%s excluded=%s",
                build.glb_file_id, build.included_sections,
                [e.section_id for e in build.excluded_sections],
            )
            assert build.persisted is False

            confirm = await svc.confirm_floor_mesh(floor_id, build.glb_file_id)
            logger.info("confirm: mesh_file_glb=%s", confirm.mesh_file_glb)

        glb_path = os.path.join(upload_dir, "models", f"floor_{floor_id}.glb")
        mesh = trimesh.load(glb_path, force="mesh")
        assert len(mesh.vertices) > 0 and len(mesh.faces) > 0, "GLB is empty!"

        print("\n=== Demo floor assembled successfully ===")
        print(f"  floor_id    : {floor_id}")
        print(f"  GLB file    : {os.path.abspath(glb_path)}")
        print(f"  servable URL: /api/v1/uploads/models/floor_{floor_id}.glb")
        print(f"  mesh        : {len(mesh.vertices)} vertices, {len(mesh.faces)} faces")
        print("  Open the URL in the 3D viewer (or the GLB file in any glTF viewer).")
    finally:
        if not args.keep_intermediate:
            for path in generated:
                try:
                    os.remove(path)
                except OSError:
                    pass
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
