"""
API Router initialization - combines all route modules
"""

from fastapi import APIRouter

from app.api.auth import router as auth_router, users_router
from app.api.upload import router as upload_router
from app.api.reconstruction import router as reconstruction_router
from app.api.navigation import router as navigation_router
from app.api.transitions import router as transitions_router
from app.api.buildings import router as buildings_router
from app.api.buildings_hierarchy import router as buildings_hierarchy_router
from app.api.floors import router as floors_router
from app.api.sections import router as sections_router
from app.api.floor_schema import router as floor_schema_router
from app.api.stitching import router as stitching_router
from app.api.floor_transitions import router as floor_transitions_router
from app.api.floor_assembly import router as floor_assembly_router
from app.api.floor_nav import router as floor_nav_router
from app.api.building_assembly import router as building_assembly_router
from app.api.building_scene import router as building_scene_router
from app.api.building_nav import router as building_nav_router

# Main API router
router = APIRouter()

# Include all sub-routers
router.include_router(auth_router)
router.include_router(users_router)
router.include_router(upload_router)
router.include_router(reconstruction_router)
router.include_router(navigation_router)
router.include_router(transitions_router)
router.include_router(buildings_router)
router.include_router(buildings_hierarchy_router)
router.include_router(floors_router)
router.include_router(sections_router)
router.include_router(floor_schema_router)
router.include_router(stitching_router)
router.include_router(floor_transitions_router)
router.include_router(floor_assembly_router)
router.include_router(floor_nav_router)
router.include_router(building_assembly_router)
router.include_router(building_scene_router)
router.include_router(building_nav_router)


# Common info endpoint

@router.get("/common/info", tags=["Common"])
async def get_info():
    """
    Информация о сервере

    Используется для проверки доступности API
    """
    return {
        "name": "Diplom3D API",
        "version": "0.1.0",
        "status": "online"
    }
