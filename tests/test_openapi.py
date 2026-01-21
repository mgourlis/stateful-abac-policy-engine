
import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_openapi_schema(ac: AsyncClient):
    response = await ac.get("/openapi.json")
    assert response.status_code == 200, "Failed to fetch openapi.json"
    
    data = response.json()
    assert data.get('info', {}).get('title') == "Stateful ABAC Policy Engine"
    assert 'version' in data.get('info', {})
    
    expected_tags = {"auth", "realms"}
    found_tags = {t['name'] for t in data.get('tags', [])}
    
    assert expected_tags.issubset(found_tags), f"Missing tags. Found: {found_tags}"
