"""
Transition service orchestration.
"""

from __future__ import annotations

import logging
from typing import Optional

from app.db.repositories.reconstruction_repo import ReconstructionRepository
from app.db.repositories.transition_repo import TransitionRepository
from app.models.transition import (
    MultiPlanRouteRequest,
    MultiPlanRouteResponse,
    RouteSegment,
    TransitionGroupCreate,
    TransitionGroupResponse,
    TransitionGroupUpdate,
    TransitionPointCreate,
    TransitionPointResponse,
    TransitionPointUpdate,
)
from app.processing.multi_plan_graph import MultiPlanRouteResultData

logger = logging.getLogger(__name__)


class TransitionService:
    def __init__(
        self,
        transition_repo: TransitionRepository,
        reconstruction_repo: ReconstructionRepository,
    ) -> None:
        self._transition_repo = transition_repo
        self._reconstruction_repo = reconstruction_repo

    async def create_group(self, data: TransitionGroupCreate, user_id: int | None) -> TransitionGroupResponse:
        group = await self._transition_repo.create_group(
            data.building_id,
            data.type,
            data.label,
            data.target_hint_building_id,
            data.target_hint_floor_number,
            user_id,
        )
        return TransitionGroupResponse(
            id=group.id,
            building_id=group.building_id,
            type=group.type,  # type: ignore[arg-type]
            label=group.label,
            target_hint_building_id=group.target_hint_building_id,
            target_hint_floor_number=group.target_hint_floor_number,
            point_ids=[point.id for point in group.points],
            created_at=group.created_at,
        )

    async def update_group(self, group_id: int, data: TransitionGroupUpdate) -> TransitionGroupResponse | None:
        group = await self._transition_repo.update_group(
            group_id,
            data.type,
            data.label,
            data.target_hint_building_id,
            data.target_hint_floor_number,
        )
        if group is None:
            return None
        return TransitionGroupResponse(
            id=group.id,
            building_id=group.building_id,
            type=group.type,  # type: ignore[arg-type]
            label=group.label,
            target_hint_building_id=group.target_hint_building_id,
            target_hint_floor_number=group.target_hint_floor_number,
            point_ids=[point.id for point in group.points],
            created_at=group.created_at,
        )

    async def delete_group(self, group_id: int) -> bool:
        return await self._transition_repo.delete_group(group_id)

    async def list_groups_for_building(self, building_id: str) -> list[TransitionGroupResponse]:
        groups = await self._transition_repo.list_groups_by_building(building_id)
        return [
            TransitionGroupResponse(
                id=group.id,
                building_id=group.building_id,
                type=group.type,  # type: ignore[arg-type]
                label=group.label,
                target_hint_building_id=group.target_hint_building_id,
                target_hint_floor_number=group.target_hint_floor_number,
                point_ids=[point.id for point in group.points],
                created_at=group.created_at,
            )
            for group in groups
        ]

    async def list_all_groups(self) -> list[TransitionGroupResponse]:
        groups = await self._transition_repo.list_all_groups()
        return [
            TransitionGroupResponse(
                id=group.id,
                building_id=group.building_id,
                type=group.type,  # type: ignore[arg-type]
                label=group.label,
                target_hint_building_id=group.target_hint_building_id,
                target_hint_floor_number=group.target_hint_floor_number,
                point_ids=[point.id for point in group.points],
                created_at=group.created_at,
            )
            for group in groups
        ]

    async def create_point(self, data: TransitionPointCreate, user_id: int | None) -> TransitionPointResponse:
        reconstruction = await self._reconstruction_repo.get_by_id(data.reconstruction_id)
        if reconstruction is None:
            raise ValueError("reconstruction not found")
        group = await self._transition_repo.get_group(data.group_id)
        if group is None:
            raise ValueError("group not found")
        point = await self._transition_repo.create_point(
            data.reconstruction_id,
            data.group_id,
            data.position_x,
            data.position_y,
            data.geometry,
            data.label,
            user_id,
        )
        return TransitionPointResponse(
            id=point.id,
            reconstruction_id=point.reconstruction_id,
            group_id=point.group_id,
            position_x=point.position_x,
            position_y=point.position_y,
            geometry=point.geometry,
            label=point.label,
            snapped_node_id=None,
        )

    async def update_point(self, point_id: int, data: TransitionPointUpdate) -> TransitionPointResponse | None:
        point = await self._transition_repo.update_point(point_id, data.position_x, data.position_y, data.geometry, data.label)
        if point is None:
            return None
        return TransitionPointResponse(
            id=point.id,
            reconstruction_id=point.reconstruction_id,
            group_id=point.group_id,
            position_x=point.position_x,
            position_y=point.position_y,
            geometry=point.geometry,
            label=point.label,
            snapped_node_id=None,
        )

    async def delete_point(self, point_id: int) -> bool:
        return await self._transition_repo.delete_point(point_id)

    async def list_points_for_reconstruction(self, reconstruction_id: int) -> list[TransitionPointResponse]:
        points = await self._transition_repo.list_points_by_reconstruction(reconstruction_id)
        return [
            TransitionPointResponse(
                id=point.id,
                reconstruction_id=point.reconstruction_id,
                group_id=point.group_id,
                position_x=point.position_x,
                position_y=point.position_y,
                geometry=point.geometry,
                label=point.label,
                snapped_node_id=None,
            )
            for point in points
        ]

    async def list_points_for_building(self, building_id: str) -> list[TransitionPointResponse]:
        points = await self._transition_repo.list_points_by_building(building_id)
        return [
            TransitionPointResponse(
                id=point.id,
                reconstruction_id=point.reconstruction_id,
                group_id=point.group_id,
                position_x=point.position_x,
                position_y=point.position_y,
                geometry=point.geometry,
                label=point.label,
                snapped_node_id=None,
            )
            for point in points
        ]

    async def route_multi(self, request: MultiPlanRouteRequest) -> MultiPlanRouteResponse:
        if request.from_reconstruction_id == request.to_reconstruction_id:
            return MultiPlanRouteResponse(status="error", message="multi-plan route requires different reconstructions")
        return MultiPlanRouteResponse(status="no_path", message="multi-plan route processing is not wired yet", segments=[])


def to_route_response(result: MultiPlanRouteResultData) -> MultiPlanRouteResponse:
    return MultiPlanRouteResponse(
        status=result.status,  # type: ignore[arg-type]
        message=result.message,
        total_distance_meters=result.total_distance_meters,
        segments=[
            RouteSegment(
                reconstruction_id=segment.reconstruction_id,
                coordinates=segment.coordinates,
                transition_out_point_id=segment.transition_out_point_id,
            )
            for segment in result.segments
        ],
    )
