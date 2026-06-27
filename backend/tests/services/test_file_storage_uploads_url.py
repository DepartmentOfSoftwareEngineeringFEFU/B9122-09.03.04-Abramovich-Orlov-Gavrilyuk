"""Unit tests for ``FileStorage.uploads_url`` (subfeature B).

A static, pure string helper — no disk / ``upload_dir`` needed. Covers

"""

from app.services.file_storage import FileStorage


def test_uploads_url_prefixes_rel_path():
    """A normal models rel_path maps to the static uploads URL."""
    assert (
        FileStorage.uploads_url("models/floor_3.glb")
        == "/api/v1/uploads/models/floor_3.glb"
    )


def test_uploads_url_normalises_backslashes_and_leading_slash():
    """Windows separators and a leading slash collapse to single forward slashes."""
    assert (
        FileStorage.uploads_url("\\models\\x.glb")
        == "/api/v1/uploads/models/x.glb"
    )
    assert (
        FileStorage.uploads_url("/models/x.glb")
        == "/api/v1/uploads/models/x.glb"
    )
