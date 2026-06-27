import io
import pytest


def _make_jpeg_bytes() -> bytes:
    """Create minimal valid JPEG bytes for upload tests."""
    import cv2
    import numpy as np
    import tempfile
    import os
    img = np.ones((10, 10, 3), dtype=np.uint8) * 200
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
        tmppath = f.name
    cv2.imwrite(tmppath, img)
    with open(tmppath, "rb") as f:
        data = f.read()
    os.unlink(tmppath)
    return data


@pytest.mark.asyncio
async def test_upload_plan_photo_without_auth_returns_403(client):
    response = await client.post(
        "/api/v1/upload/plan-photo/",
        files={"file": ("test.jpg", b"fake", "image/jpeg")},
    )
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_upload_user_mask_without_auth_returns_403(client):
    response = await client.post(
        "/api/v1/upload/user-mask/",
        files={"file": ("test.jpg", b"fake", "image/jpeg")},
    )
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_upload_plan_photo_invalid_extension_returns_400(client, auth_headers):
    response = await client.post(
        "/api/v1/upload/plan-photo/",
        files={"file": ("test.bmp", b"fake bmp content", "image/bmp")},
        headers=auth_headers,
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_upload_plan_photo_with_auth_and_valid_image_returns_200(client, auth_headers, tmp_path, monkeypatch):
    """Upload with valid JPEG — override save path to avoid disk writes."""
    from app.services.file_storage import FileStorage

    async def mock_save_uploaded_file(self, file_content, filename, subfolder=""):
        return "mock-file-id"

    monkeypatch.setattr(FileStorage, "save_uploaded_file", mock_save_uploaded_file)

    from app.db.repositories.reconstruction_repo import ReconstructionRepository

    async def mock_create_file(self, **kwargs):
        from app.db.models.reconstruction import UploadedFile
        from datetime import datetime
        return UploadedFile(
            id="mock-file-id",
            filename="test.jpg",
            file_path="plans/mock-file-id.jpg",
            url="/api/v1/uploads/plans/mock-file-id.jpg",
            file_type=1,
            uploaded_by=1,
            uploaded_at=datetime.utcnow(),
        )

    monkeypatch.setattr(ReconstructionRepository, "create_uploaded_file", mock_create_file)

    jpeg_bytes = _make_jpeg_bytes()
    response = await client.post(
        "/api/v1/upload/plan-photo/",
        files={"file": ("test.jpg", jpeg_bytes, "image/jpeg")},
        headers=auth_headers,
    )
    assert response.status_code == 200
