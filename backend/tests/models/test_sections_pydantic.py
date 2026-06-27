"""
Pydantic validation tests for Section models.
"""

import pytest
from pydantic import ValidationError

from app.models.sections import (
    ReplaceSectionsRequest,
    SectionGeometry,
    SectionPayloadItem,
)


def test_section_geometry_valid_4_points():
    geom = SectionGeometry(points=[[0.1, 0.1], [0.4, 0.1], [0.4, 0.5], [0.1, 0.5]])
    assert len(geom.points) == 4


def test_section_geometry_too_few_points():
    # min_length=3 (relaxed from the quad for the Floor Editor polygon
    # tool), so fewer than 3 vertices must be rejected.
    with pytest.raises(ValidationError):
        SectionGeometry(points=[[0.1, 0.1], [0.4, 0.1]])


def test_section_geometry_five_points_allowed():
    # Floor Editor's polygon tool can produce N>4 vertices.
    geom = SectionGeometry(
        points=[[0.1, 0.1], [0.4, 0.1], [0.4, 0.5], [0.25, 0.6], [0.1, 0.5]]
    )
    assert len(geom.points) == 5


def test_section_geometry_too_many_points():
    with pytest.raises(ValidationError):
        SectionGeometry(points=[[i / 100, 0.5] for i in range(33)])


def test_section_geometry_point_out_of_range():
    with pytest.raises(ValidationError):
        SectionGeometry(points=[[1.5, 0.1], [0.4, 0.1], [0.4, 0.5], [0.1, 0.5]])


def test_section_geometry_negative_coord_rejected():
    with pytest.raises(ValidationError):
        SectionGeometry(points=[[-0.1, 0.1], [0.4, 0.1], [0.4, 0.5], [0.1, 0.5]])


def test_section_geometry_edge_values_valid():
    geom = SectionGeometry(points=[[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]])
    assert geom.points[0] == [0.0, 0.0]


def test_section_payload_item_defaults():
    item = SectionPayloadItem(
        number=1,
        geometry=SectionGeometry(
            points=[[0.1, 0.1], [0.4, 0.1], [0.4, 0.5], [0.1, 0.5]]
        ),
    )
    assert item.section_type == 1
    assert item.reconstruction_id is None


def test_section_payload_item_invalid_number_zero():
    with pytest.raises(ValidationError):
        SectionPayloadItem(
            number=0,
            geometry=SectionGeometry(
                points=[[0.1, 0.1], [0.4, 0.1], [0.4, 0.5], [0.1, 0.5]]
            ),
        )


def test_section_payload_item_invalid_section_type():
    with pytest.raises(ValidationError):
        SectionPayloadItem(
            number=1,
            geometry=SectionGeometry(
                points=[[0.1, 0.1], [0.4, 0.1], [0.4, 0.5], [0.1, 0.5]]
            ),
            section_type=11,
        )


def test_replace_sections_request_valid():
    req = ReplaceSectionsRequest(
        sections=[
            SectionPayloadItem(
                number=1,
                geometry=SectionGeometry(
                    points=[[0.1, 0.1], [0.4, 0.1], [0.4, 0.5], [0.1, 0.5]]
                ),
            )
        ]
    )
    assert len(req.sections) == 1


def test_replace_sections_request_too_many_sections():
    item = SectionPayloadItem(
        number=1,
        geometry=SectionGeometry(
            points=[[0.1, 0.1], [0.4, 0.1], [0.4, 0.5], [0.1, 0.5]]
        ),
    )
    with pytest.raises(ValidationError):
        ReplaceSectionsRequest(sections=[item] * 51)
