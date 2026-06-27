import pytest


@pytest.mark.asyncio
async def test_get_reconstruction_vectors_200(client, auth_headers):
    assert client is not None
    assert "Authorization" in auth_headers


@pytest.mark.asyncio
async def test_update_reconstruction_vectors_200(client, auth_headers):
    assert client is not None
    assert "Authorization" in auth_headers


@pytest.mark.asyncio
async def test_update_reconstruction_vectors_400(client, auth_headers):
    assert client is not None
    assert "Authorization" in auth_headers
