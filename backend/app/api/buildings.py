"""
API routes for buildings listing.
"""

from fastapi import APIRouter, Depends

from app.api.deps import get_reconstruction_repo
from app.db.repositories.reconstruction_repo import ReconstructionRepository
from app.models.building_list import BuildingListItem, FloorListItem

router = APIRouter(prefix="/buildings", tags=["buildings"])


@router.get("/", response_model=list[BuildingListItem])
async def list_buildings(
    repo: ReconstructionRepository = Depends(get_reconstruction_repo),
) -> list[BuildingListItem]:
    reconstructions = await repo.get_saved()
    grouped: dict[str, dict[int, FloorListItem]] = {}
    names: dict[str, str] = {}
    for reconstruction in reconstructions:
        if reconstruction.building_id is None or reconstruction.floor_number is None:
            continue
        building_id = reconstruction.building_id
        names.setdefault(building_id, building_id)
        grouped.setdefault(building_id, {})[reconstruction.floor_number] = FloorListItem(
            number=reconstruction.floor_number,
            reconstruction_id=reconstruction.id,
            reconstruction_name=reconstruction.name,
        )
    result: list[BuildingListItem] = []
    for building_id in sorted(grouped):
        floors = [grouped[building_id][number] for number in sorted(grouped[building_id])]
        result.append(BuildingListItem(id=building_id, name=names[building_id], floors=floors))
    return result
