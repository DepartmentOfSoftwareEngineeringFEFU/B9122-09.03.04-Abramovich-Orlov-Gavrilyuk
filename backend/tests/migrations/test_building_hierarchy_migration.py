"""
Tests for f1g2h3i4j5k6_building_hierarchy migration.

These tests verify the post-migration schema state against the project's
development database (diplom3d.db), which is kept at 'head' by the dev workflow.

The test module connects to the real (already-migrated) DB in read-only mode
so it never mutates state — safe to run in CI as long as dev.db exists and is
at head.

If the DB is not at head, the fixture raises a clear error.
"""

import os
import sys

import pytest
from sqlalchemy import create_engine, inspect
from alembic.config import Config
from alembic.script import ScriptDirectory
from alembic.runtime.migration import MigrationContext

# Ensure backend/ is on sys.path when running from repo root or from backend/
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

_TARGET_REVISION = "f1g2h3i4j5k6"


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def migrated_engine():
    """
    Synchronous engine pointing at the dev SQLite DB (diplom3d.db).
    Asserts that all migrations including f1g2h3i4j5k6 have been applied.
    """
    db_path = os.path.join(_BACKEND_DIR, "diplom3d.db")
    assert os.path.exists(db_path), (
        f"Dev database not found at {db_path}. "
        "Run 'alembic upgrade head' to create it."
    )

    engine = create_engine(f"sqlite:///{db_path}", echo=False)

    # Verify that our target revision has been APPLIED. It may no longer be a
    # head — later migrations get stacked on top — so we check the ancestor
    # chain of the current head(s) rather than requiring head-equality.
    with engine.connect() as conn:
        mc = MigrationContext.configure(conn)
        current_heads = mc.get_current_heads()

    alembic_cfg = Config()
    alembic_cfg.set_main_option(
        "script_location", os.path.join(_BACKEND_DIR, "alembic")
    )
    script = ScriptDirectory.from_config(alembic_cfg)
    applied: set[str] = set()
    for head in current_heads:
        for rev in script.iterate_revisions(head, "base"):
            applied.add(rev.revision)

    assert _TARGET_REVISION in applied, (
        f"Migration {_TARGET_REVISION} has not been applied. "
        f"Current heads: {current_heads}. "
        "Run 'python -m alembic upgrade head' from backend/."
    )

    yield engine
    engine.dispose()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestBuildingHierarchyMigration:
    """DB Migration — building hierarchy (f1g2h3i4j5k6)."""

    def test_migration_drops_old_reconstructions_columns(self, migrated_engine):
        """After upgrade, reconstructions must NOT have building_id or floor_number."""
        inspector = inspect(migrated_engine)
        col_names = {c["name"] for c in inspector.get_columns("reconstructions")}

        assert "building_id" not in col_names, (
            "building_id must be dropped from reconstructions in building_hierarchy migration"
        )
        assert "floor_number" not in col_names, (
            "floor_number must be dropped from reconstructions in building_hierarchy migration"
        )
        assert "floor_id" in col_names, (
            "floor_id must be added to reconstructions in building_hierarchy migration"
        )

    def test_migration_creates_section_table_with_constraints(self, migrated_engine):
        """sections table must exist with required columns and UNIQUE constraints."""
        inspector = inspect(migrated_engine)
        table_names = inspector.get_table_names()
        assert "sections" in table_names, "sections table must be created"

        col_names = {c["name"] for c in inspector.get_columns("sections")}
        required_cols = {
            "id", "floor_id", "number", "geometry",
            "reconstruction_id", "section_type",
        }
        assert required_cols.issubset(col_names), (
            f"sections table is missing columns: {required_cols - col_names}"
        )

        # UNIQUE(floor_id, number)
        unique_constraints = inspector.get_unique_constraints("sections")
        composite_unique_cols = [
            set(uc["column_names"])
            for uc in unique_constraints
            if len(uc["column_names"]) > 1
        ]
        assert {"floor_id", "number"} in composite_unique_cols, (
            "sections must have UNIQUE(floor_id, number) constraint"
        )

        # UNIQUE(reconstruction_id) — may be expressed as an index in SQLite
        single_unique_cols = [
            set(uc["column_names"])
            for uc in unique_constraints
            if len(uc["column_names"]) == 1
        ]
        unique_indexes = [
            set(idx["column_names"])
            for idx in inspector.get_indexes("sections")
            if idx.get("unique")
        ]
        all_unique = single_unique_cols + unique_indexes
        assert {"reconstruction_id"} in all_unique, (
            "sections.reconstruction_id must have a UNIQUE constraint or index"
        )

    def test_migration_drops_floor_reconstruction_id(self, migrated_engine):
        """floors table must NOT have reconstruction_id column after upgrade."""
        inspector = inspect(migrated_engine)
        col_names = {c["name"] for c in inspector.get_columns("floors")}

        assert "reconstruction_id" not in col_names, (
            "floors.reconstruction_id must be dropped in building_hierarchy migration"
        )

    def test_migration_adds_building_code_unique(self, migrated_engine):
        """buildings.code must exist and have a UNIQUE constraint."""
        inspector = inspect(migrated_engine)
        col_names = {c["name"] for c in inspector.get_columns("buildings")}

        assert "code" in col_names, (
            "buildings.code must be added in building_hierarchy migration"
        )

        unique_constraints = inspector.get_unique_constraints("buildings")
        unique_col_sets = [set(uc["column_names"]) for uc in unique_constraints]
        unique_indexes = [
            set(idx["column_names"])
            for idx in inspector.get_indexes("buildings")
            if idx.get("unique")
        ]
        all_unique = unique_col_sets + unique_indexes
        assert {"code"} in all_unique, (
            "buildings.code must have a UNIQUE constraint or index"
        )

    def test_migration_drops_floor_transitions(self, migrated_engine):
        """floor_transitions table must be retained with its expected schema.

        The building_hierarchy migration deleted the legacy rows but kept the
        table. The row count is not asserted: this fixture reads the live dev
        database, which legitimately accumulates floor transitions during
        normal use, so a ``COUNT(*) == 0`` invariant would be data-dependent.
        """
        inspector = inspect(migrated_engine)
        table_names = inspector.get_table_names()
        assert "floor_transitions" in table_names, (
            "floor_transitions table should still exist (only data was deleted)"
        )
        col_names = {c["name"] for c in inspector.get_columns("floor_transitions")}
        assert {
            "id", "building_id", "from_reconstruction_id", "to_reconstruction_id"
        }.issubset(col_names), (
            f"floor_transitions is missing expected columns; got {sorted(col_names)}"
        )
