import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.db.models.reconstruction import Reconstruction, UploadedFile
from app.db.models.section import Section
from app.db.models.building import Floor
from app.db.repositories.base_repository import BaseRepository

logger = logging.getLogger(__name__)


class ReconstructionRepository(BaseRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def create_uploaded_file(
        self,
        file_id: str,
        filename: str,
        file_path: str,
        url: str,
        file_type: int,
        user_id: int,
    ) -> UploadedFile:
        """INSERT в uploaded_files."""
        logger.debug(
            "create_uploaded_file: file_id=%s, filename=%s, file_type=%d",
            file_id,
            filename,
            file_type,
        )
        db_file = UploadedFile(
            id=file_id,
            filename=filename,
            file_path=file_path,
            url=url,
            file_type=file_type,
            uploaded_by=user_id,
            uploaded_at=datetime.utcnow(),
        )
        self._session.add(db_file)
        await self._session.commit()
        await self._session.refresh(db_file)
        return db_file

    async def create_reconstruction(
        self,
        plan_file_id: str,
        mask_file_id: str,
        user_id: int,
        status: int = 2,
    ) -> Reconstruction:
        """INSERT в reconstructions, status=2 (processing)."""
        logger.debug(
            "create_reconstruction: plan=%s, mask=%s, user=%d",
            plan_file_id,
            mask_file_id,
            user_id,
        )
        reconstruction = Reconstruction(
            plan_file_id=plan_file_id,
            mask_file_id=mask_file_id,
            status=status,
            created_by=user_id,
            created_at=datetime.utcnow(),
        )
        self._session.add(reconstruction)
        await self._session.commit()
        await self._session.refresh(reconstruction)
        return reconstruction

    async def get_by_id(self, reconstruction_id: int) -> Optional[Reconstruction]:
        """SELECT by PK. Returns None if not found."""
        logger.debug("get_by_id: reconstruction_id=%d", reconstruction_id)
        result = await self._session.execute(
            select(Reconstruction)
            .options(joinedload(Reconstruction.plan_file))
            .options(joinedload(Reconstruction.mask_file))
            .options(selectinload(Reconstruction.floor).selectinload(Floor.building))
            .where(Reconstruction.id == reconstruction_id)
        )
        return result.scalar_one_or_none()

    async def update_mesh(
        self,
        reconstruction_id: int,
        obj_path: Optional[str],
        glb_path: Optional[str],
        status: int,
        error_message: Optional[str] = None,
    ) -> Optional[Reconstruction]:
        """UPDATE mesh_file_id_obj, mesh_file_id_glb, status, error_message."""
        logger.debug(
            "update_mesh: reconstruction_id=%d, status=%d", reconstruction_id, status
        )
        reconstruction = await self._session.get(Reconstruction, reconstruction_id)
        if not reconstruction:
            return None
        reconstruction.mesh_file_id_obj = obj_path
        reconstruction.mesh_file_id_glb = glb_path
        reconstruction.status = status
        reconstruction.error_message = error_message
        await self._session.commit()
        await self._session.refresh(reconstruction)
        return reconstruction

    async def update_name(
        self,
        reconstruction_id: int,
        name: str,
    ) -> Optional[Reconstruction]:
        """UPDATE name. Returns None if not found."""
        logger.debug(
            "update_name: reconstruction_id=%d, name=%s", reconstruction_id, name
        )
        reconstruction = await self._session.get(Reconstruction, reconstruction_id)
        if not reconstruction:
            return None
        reconstruction.name = name
        await self._session.commit()
        await self._session.refresh(reconstruction)
        return reconstruction

    async def update_reconstruction(
        self,
        reconstruction_id: int,
        name: str,
        floor_id: Optional[int] = None,
    ) -> Optional[Reconstruction]:
        """UPDATE name and optionally floor_id. Returns None if not found."""
        logger.debug(
            "update_reconstruction: reconstruction_id=%d, name=%s, floor_id=%s",
            reconstruction_id, name, floor_id,
        )
        reconstruction = await self._session.get(Reconstruction, reconstruction_id)
        if not reconstruction:
            return None
        reconstruction.name = name
        if floor_id is not None:
            reconstruction.floor_id = floor_id
        await self._session.commit()
        await self._session.refresh(reconstruction)
        return reconstruction

    async def update_floor_id(
        self,
        reconstruction_id: int,
        floor_id: Optional[int],
    ) -> Optional[Reconstruction]:
        """UPDATE floor_id (partial). Returns None if reconstruction not found."""
        logger.debug(
            "update_floor_id: reconstruction_id=%d, floor_id=%s",
            reconstruction_id, floor_id,
        )
        reconstruction = await self._session.get(Reconstruction, reconstruction_id)
        if not reconstruction:
            return None
        reconstruction.floor_id = floor_id
        await self._session.commit()
        await self._session.refresh(reconstruction)
        return reconstruction

    async def get_saved(
        self,
        user_id: Optional[int] = None,
        floor_id: Optional[int] = None,
        status: Optional[int] = None,
        unbound: bool = False,
        search: Optional[str] = None,
    ) -> list[Reconstruction]:
        """SELECT WHERE name IS NOT NULL ORDER BY updated_at DESC.

        Optional filters: floor_id, status, unbound, and a name search substring.
        """
        logger.debug(
            "get_saved: user_id=%s, floor_id=%s, status=%s, unbound=%s, search=%s",
            user_id, floor_id, status, unbound, search,
        )
        query = (
            select(Reconstruction)
            .options(joinedload(Reconstruction.plan_file))
            .options(joinedload(Reconstruction.mask_file))
            .options(selectinload(Reconstruction.section))
            .options(selectinload(Reconstruction.floor).selectinload(Floor.building))
            .where(Reconstruction.name.isnot(None))
            .order_by(Reconstruction.updated_at.desc())
        )
        if user_id is not None:
            query = query.where(Reconstruction.created_by == user_id)
        if floor_id is not None:
            query = query.where(Reconstruction.floor_id == floor_id)
        if status is not None:
            query = query.where(Reconstruction.status == status)
        if search is not None:
            query = query.where(Reconstruction.name.ilike(f"%{search}%"))
        if unbound:
            # Only reconstructions not linked to any section
            query = (
                query
                .outerjoin(Section, Section.reconstruction_id == Reconstruction.id)
                .where(Section.id.is_(None))
            )
        result = await self._session.execute(query)
        return list(result.scalars().unique().all())

    async def list_unbound_for_floor(self, floor_id: int) -> list[Reconstruction]:
        """SELECT reconstructions with floor_id=?, status=Done(3), not in any section.

        LEFT OUTER JOIN sections on sections.reconstruction_id = reconstructions.id,
        keep rows WHERE sections.id IS NULL.
        """
        logger.debug("list_unbound_for_floor: floor_id=%d", floor_id)
        result = await self._session.execute(
            select(Reconstruction)
            .outerjoin(Section, Section.reconstruction_id == Reconstruction.id)
            .where(
                Reconstruction.floor_id == floor_id,
                Reconstruction.status == 3,  # Done
                Section.id.is_(None),
            )
            .order_by(Reconstruction.updated_at.desc())
        )
        return list(result.scalars().unique().all())

    async def get_with_relations(self, reconstruction_id: int) -> Optional[Reconstruction]:
        """SELECT by PK with full relations: floor→building + linked section."""
        logger.debug("get_with_relations: reconstruction_id=%d", reconstruction_id)
        from app.db.models.building import Floor  # noqa: PLC0415

        result = await self._session.execute(
            select(Reconstruction)
            .options(
                selectinload(Reconstruction.floor).selectinload(Floor.building),
            )
            .options(selectinload(Reconstruction.section))
            .options(joinedload(Reconstruction.plan_file))
            .options(joinedload(Reconstruction.mask_file))
            .where(Reconstruction.id == reconstruction_id)
        )
        return result.scalar_one_or_none()

    async def delete(self, reconstruction_id: int) -> bool:
        """DELETE. Returns True if deleted, False if not found."""
        logger.debug("delete: reconstruction_id=%d", reconstruction_id)
        reconstruction = await self._session.get(Reconstruction, reconstruction_id)
        if not reconstruction:
            return False
        await self._session.delete(reconstruction)
        await self._session.commit()
        return True

    async def update_vectorization_data(
        self,
        reconstruction_id: int,
        vectorization_json: str,
    ) -> Optional[Reconstruction]:
        """UPDATE vectorization_data field. Returns None if not found."""
        logger.debug("update_vectorization_data: reconstruction_id=%d", reconstruction_id)
        reconstruction = await self._session.get(Reconstruction, reconstruction_id)
        if not reconstruction:
            return None
        reconstruction.vectorization_data = vectorization_json
        reconstruction.updated_at = datetime.utcnow()
        await self._session.commit()
        await self._session.refresh(reconstruction)
        return reconstruction

    async def update_control_points(
        self,
        reconstruction_id: int,
        points: list[dict],
    ) -> Optional[Reconstruction]:
        """UPDATE section-local control_points field. Returns None if not found."""
        logger.debug("update_control_points: reconstruction_id=%d", reconstruction_id)
        reconstruction = await self._session.get(Reconstruction, reconstruction_id)
        if not reconstruction:
            return None
        reconstruction.control_points = points
        reconstruction.updated_at = datetime.utcnow()
        await self._session.commit()
        await self._session.refresh(reconstruction)
        return reconstruction
