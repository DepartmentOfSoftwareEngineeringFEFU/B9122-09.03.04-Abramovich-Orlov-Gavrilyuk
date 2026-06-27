"""
Pydantic validation tests for Building models.
"""

import pytest
from pydantic import ValidationError

from app.models.buildings import (
    BuildingCreateRequest,
    BuildingDetailResponse,
    BuildingResponse,
    BuildingUpdateRequest,
)


def test_building_create_request_normalises_code_to_uppercase():
    req = BuildingCreateRequest(code="d", name="Корпус D")
    assert req.code == "D"


def test_building_create_request_normalises_mixed_case():
    req = BuildingCreateRequest(code="Ab", name="X")
    assert req.code == "AB"


def test_building_create_request_invalid_code_too_long():
    with pytest.raises(ValidationError):
        BuildingCreateRequest(code="TOOLNG", name="X")


def test_building_create_request_invalid_code_with_digits():
    with pytest.raises(ValidationError):
        BuildingCreateRequest(code="D1", name="X")


def test_building_create_request_invalid_empty_name():
    with pytest.raises(ValidationError):
        BuildingCreateRequest(code="D", name="")


def test_building_create_request_address_optional():
    req = BuildingCreateRequest(code="D", name="Корпус D")
    assert req.address is None


def test_building_create_request_address_too_long():
    with pytest.raises(ValidationError):
        BuildingCreateRequest(code="D", name="X", address="A" * 513)


def test_building_update_request_all_optional():
    req = BuildingUpdateRequest()
    assert req.name is None
    assert req.address is None


def test_building_update_request_partial():
    req = BuildingUpdateRequest(name="New Name")
    assert req.name == "New Name"
    assert req.address is None
