"""
Sanity check: report whether the DB has any "published" buildings,
i.e. buildings with at least one Section bound to a Reconstruction
whose status == Done (3).

Highlights ДВФУ (case-insensitive substring match in Building.name) for
demo/VKR purposes.

Exit codes:
  0 - at least one ДВФУ building is published
  1 - no ДВФУ building published (or no published buildings at all)

Usage (from project root):
  python scripts/check_dvfu_published.py
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

# Load .env from backend/ so settings pick up DATABASE_URL just like the app.
try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv(BACKEND_DIR / ".env")
except Exception:
    pass

from sqlalchemy import create_engine, func, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.db.models.building import Building, Floor  # noqa: E402
from app.db.models.section import Section  # noqa: E402
from app.db.models.reconstruction import Reconstruction  # noqa: E402

# Status code that means reconstruction is fully built (see Reconstruction.status)
DONE_STATUS = 3
DVFU_NEEDLE = "двфу"

SEED_CHECKLIST = """\
[!] No published buildings found.
To seed data manually:
  1. Login as admin at http://localhost:5173/login
  2. Go to /admin/buildings -> create building "ДВФУ корпус D" with code "D"
  3. Add floor #7, upload plan
  4. Go to /admin/floor-editor -> run 5-step wizard
  5. Bind plan to a reconstruction in step 5
  6. Wait for reconstruction.status == Done (3)
  7. Re-run this script
"""


def _to_sync_url(url: str) -> str:
    """Convert an async SQLAlchemy URL to its sync counterpart and resolve
    SQLite relative paths against the backend/ directory."""
    sync = (
        url
        .replace("sqlite+aiosqlite", "sqlite")
        .replace("postgresql+asyncpg", "postgresql+psycopg2")
    )
    if sync.startswith("sqlite:///./"):
        rel = sync[len("sqlite:///./"):]
        abs_path = (BACKEND_DIR / rel).resolve()
        sync = f"sqlite:///{abs_path}"
    return sync


def main() -> int:
    db_url = _to_sync_url(settings.DATABASE_URL)
    print(f"=== Published buildings check ===")
    print(f"DB URL: {db_url}")

    engine = create_engine(db_url, future=True)

    with Session(engine) as session:
        buildings = session.execute(select(Building)).scalars().all()
        total = len(buildings)
        print(f"Total buildings: {total}")

        published: list[tuple[Building, int, int]] = []
        for b in buildings:
            floor_count = session.execute(
                select(func.count(Floor.id)).where(Floor.building_id == b.id)
            ).scalar_one()

            pub_section_count = session.execute(
                select(func.count(Section.id))
                .join(Floor, Section.floor_id == Floor.id)
                .join(Reconstruction, Section.reconstruction_id == Reconstruction.id)
                .where(Floor.building_id == b.id)
                .where(Reconstruction.status == DONE_STATUS)
            ).scalar_one()

            if pub_section_count > 0:
                published.append((b, floor_count, pub_section_count))

        print(f"Published buildings (with >=1 Done section): {len(published)}")
        for b, fc, sc in published:
            print(
                f"  - id={b.id} code=\"{b.code}\" name=\"{b.name}\" "
                f"-- floors: {fc}, published sections: {sc}"
            )

        dvfu_published = [t for t in published if DVFU_NEEDLE in t[0].name.lower()]
        dvfu_total = [b for b in buildings if DVFU_NEEDLE in b.name.lower()]

        print(
            f'Building "ДВФУ" candidates: {len(dvfu_total)} '
            f"(published: {len(dvfu_published)})"
        )

        if not published:
            print()
            print(SEED_CHECKLIST)
            return 1

        if not dvfu_published:
            print()
            print("[!] No published ДВФУ building found.")
            print("    There are other published buildings, but none whose name contains 'ДВФУ'.")
            return 1

        print("OK: at least one ДВФУ building is published.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
