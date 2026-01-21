import pytest
import time
import sys
import os

# Add SDK to path
sys.path.append(os.path.abspath("python-sdk/src"))

from httpx import ASGITransport
from stateful_abac_sdk import StatefulABACClient
from app.main import app

@pytest.mark.asyncio
async def test_realm_name_get_sdk():
    # Use ASGITransport to point to the local FastAPI app
    transport = ASGITransport(app=app)
    realm_name = f"test-realm-name-sdk-{int(time.time())}"
    client = StatefulABACClient("http://test/api/v1", realm=realm_name, transport=transport)
    
    async with client.connect(token=None):
        # connect() auto-provisions the realm, so we just get it
        realm = await client.realms.get()
        assert realm.name == realm_name
        realm_id = realm.id
        print(f"Realm ID: {realm_id}")
        
        # Verify get() fetches correctly
        realm_fetched = await client.realms.get()
        assert realm_fetched.id == realm_id
        assert realm_fetched.name == realm_name
        print("Success fetching realm")
        
        # Cleanup
        print(f"Cleaning up realm ID: {realm_id}")
        await client.request("DELETE", f"/realms/{realm_id}")
        print("Cleanup done")

if __name__ == "__main__":
    import asyncio
    asyncio.run(test_realm_name_get_sdk())
