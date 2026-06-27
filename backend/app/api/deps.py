from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.db.repositories.building_repo import BuildingRepository
from app.db.repositories.floor_repo import FloorRepository
from app.db.repositories.reconstruction_repo import ReconstructionRepository
from app.db.repositories.section_repo import SectionRepository
from app.db.repositories.transition_repo import TransitionRepository
from app.db.repositories.user_repository import UserRepository
from app.db.repositories.floor_transition_repo import FloorTransitionRepository
from app.db.repositories.floor_connector_repo import FloorConnectorRepository
from app.services.building_assembly_service import BuildingAssemblyService
from app.services.building_nav_service import BuildingNavService
from app.services.building_scene_service import BuildingSceneService
from app.services.building_service import BuildingService
from app.services.floor_assembly_service import FloorAssemblyService
from app.services.floor_nav_service import FloorNavService
from app.services.floor_schema_service import FloorSchemaService
from app.services.floor_service import FloorService
from app.services.mask_service import MaskService
from app.services.reconstruction_service import ReconstructionService
from app.services.nav_service import NavService
from app.services.file_storage import FileStorage
from app.services.section_service import SectionService
from app.services.stitching_service import StitchingService
from app.services.transition_service import TransitionService
from app.services.floor_transition_service import FloorTransitionService


async def get_reconstruction_repo(
    session: AsyncSession = Depends(get_db),
) -> ReconstructionRepository:
    return ReconstructionRepository(session)


async def get_transition_repo(
    session: AsyncSession = Depends(get_db),
) -> TransitionRepository:
    return TransitionRepository(session)


async def get_user_repo(
    session: AsyncSession = Depends(get_db),
) -> UserRepository:
    return UserRepository(session)


async def get_mask_service(
    repo: ReconstructionRepository = Depends(get_reconstruction_repo),
) -> MaskService:
    return MaskService(upload_dir=str(settings.UPLOAD_DIR))


async def get_nav_service() -> NavService:
    """Dependency factory for NavService."""
    return NavService(upload_dir=str(settings.UPLOAD_DIR))


async def get_file_storage() -> FileStorage:
    """Dependency factory for FileStorage."""
    return FileStorage(upload_dir=str(settings.UPLOAD_DIR))


async def get_floor_transition_repo(
    session: AsyncSession = Depends(get_db),
) -> FloorTransitionRepository:
    return FloorTransitionRepository(session)


async def get_reconstruction_service(
    repo: ReconstructionRepository = Depends(get_reconstruction_repo),
    storage: FileStorage = Depends(get_file_storage),
    transition_repo: FloorTransitionRepository = Depends(get_floor_transition_repo),
) -> ReconstructionService:
    return ReconstructionService(
        repo=repo,
        storage=storage,
        transition_repo=transition_repo,
    )


async def get_transition_service(
    transition_repo: TransitionRepository = Depends(get_transition_repo),
    reconstruction_repo: ReconstructionRepository = Depends(get_reconstruction_repo),
) -> TransitionService:
    return TransitionService(transition_repo, reconstruction_repo)


async def get_stitching_service(
    repo: ReconstructionRepository = Depends(get_reconstruction_repo),
) -> StitchingService:
    """Dependency factory for StitchingService."""
    return StitchingService(reconstruction_repo=repo)


async def get_floor_transition_service(
    repo: FloorTransitionRepository = Depends(get_floor_transition_repo),
    recon_repo: ReconstructionRepository = Depends(get_reconstruction_repo),
) -> FloorTransitionService:
    return FloorTransitionService(repo, recon_repo)


async def get_current_user():
    """Placeholder for current user dependency."""
    # TODO: Implement proper user authentication
    return type('User', (), {'id': 1})()


# Building hierarchy deps


async def get_building_repo(
    session: AsyncSession = Depends(get_db),
) -> BuildingRepository:
    return BuildingRepository(session)


async def get_floor_repo(
    session: AsyncSession = Depends(get_db),
) -> FloorRepository:
    return FloorRepository(session)


async def get_section_repo(
    session: AsyncSession = Depends(get_db),
) -> SectionRepository:
    return SectionRepository(session)


async def get_building_service(
    building_repo: BuildingRepository = Depends(get_building_repo),
    floor_repo: FloorRepository = Depends(get_floor_repo),
    section_repo: SectionRepository = Depends(get_section_repo),
    reconstruction_repo: ReconstructionRepository = Depends(get_reconstruction_repo),
) -> BuildingService:
    return BuildingService(
        building_repo=building_repo,
        floor_repo=floor_repo,
        section_repo=section_repo,
        reconstruction_repo=reconstruction_repo,
    )


async def get_floor_service(
    building_repo: BuildingRepository = Depends(get_building_repo),
    floor_repo: FloorRepository = Depends(get_floor_repo),
) -> FloorService:
    return FloorService(
        building_repo=building_repo,
        floor_repo=floor_repo,
    )


async def get_section_service(
    floor_repo: FloorRepository = Depends(get_floor_repo),
    section_repo: SectionRepository = Depends(get_section_repo),
    reconstruction_repo: ReconstructionRepository = Depends(get_reconstruction_repo),
) -> SectionService:
    return SectionService(
        floor_repo=floor_repo,
        section_repo=section_repo,
        reconstruction_repo=reconstruction_repo,
    )


async def get_floor_schema_service(
    floor_repo: FloorRepository = Depends(get_floor_repo),
) -> FloorSchemaService:
    return FloorSchemaService(
        floor_repo=floor_repo,
        upload_dir=str(settings.UPLOAD_DIR),
    )


# Floor-stitching deps


async def get_floor_connector_repo(
    session: AsyncSession = Depends(get_db),
) -> FloorConnectorRepository:
    return FloorConnectorRepository(session)


async def get_floor_assembly_service(
    floor_repo: FloorRepository = Depends(get_floor_repo),
    section_repo: SectionRepository = Depends(get_section_repo),
    reconstruction_repo: ReconstructionRepository = Depends(get_reconstruction_repo),
    connector_repo: FloorConnectorRepository = Depends(get_floor_connector_repo),
    storage: FileStorage = Depends(get_file_storage),
) -> FloorAssemblyService:
    return FloorAssemblyService(
        floor_repo=floor_repo,
        section_repo=section_repo,
        reconstruction_repo=reconstruction_repo,
        connector_repo=connector_repo,
        storage=storage,
    )


async def get_floor_nav_service(
    floor_repo: FloorRepository = Depends(get_floor_repo),
    section_repo: SectionRepository = Depends(get_section_repo),
    connector_repo: FloorConnectorRepository = Depends(get_floor_connector_repo),
    storage: FileStorage = Depends(get_file_storage),
) -> FloorNavService:
    return FloorNavService(
        floor_repo=floor_repo,
        section_repo=section_repo,
        connector_repo=connector_repo,
        storage=storage,
        upload_dir=str(settings.UPLOAD_DIR),
    )


# Vertical floor-stitching deps (subfeature A)


async def get_building_assembly_service(
    building_repo: BuildingRepository = Depends(get_building_repo),
    floor_repo: FloorRepository = Depends(get_floor_repo),
    storage: FileStorage = Depends(get_file_storage),
) -> BuildingAssemblyService:
    return BuildingAssemblyService(
        building_repo=building_repo,
        floor_repo=floor_repo,
        storage=storage,
    )


async def get_building_scene_service(
    building_repo: BuildingRepository = Depends(get_building_repo),
    floor_repo: FloorRepository = Depends(get_floor_repo),
    storage: FileStorage = Depends(get_file_storage),
) -> BuildingSceneService:
    return BuildingSceneService(
        building_repo=building_repo,
        floor_repo=floor_repo,
        storage=storage,
    )


# Multifloor-routing deps (subfeature D)


async def get_building_nav_service(
    building_repo: BuildingRepository = Depends(get_building_repo),
    floor_repo: FloorRepository = Depends(get_floor_repo),
    storage: FileStorage = Depends(get_file_storage),
) -> BuildingNavService:
    return BuildingNavService(
        building_repo=building_repo,
        floor_repo=floor_repo,
        storage=storage,
        upload_dir=str(settings.UPLOAD_DIR),
    )
