import pytest
import sys
import os
import uuid
from httpx import ASGITransport
from app.main import app
from common.models import Realm

# Add SDK path
sdk_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../python-sdk/src"))
if sdk_path not in sys.path:
    sys.path.insert(0, sdk_path)

from stateful_abac_sdk import StatefulABACClient
from stateful_abac_sdk.models import RealmKeycloakConfig

@pytest.mark.asyncio
async def test_sdk_keycloak_config_crud(session):
    # 1. Setup
    unique_name = f"SDK-KC-Realm-{uuid.uuid4()}"
    transport = ASGITransport(app=app)
    client = StatefulABACClient("http://test/api/v1", realm=unique_name, transport=transport)

    kc_conf = RealmKeycloakConfig(
        server_url="https://auth.example.com",
        keycloak_realm="my-realm",
        client_id="my-client",
        client_secret="secret",
        sync_groups=True,
        sync_cron="*/10 * * * *"
    )

    async with client.connect(token=None):
        # 1. Update Realm with Keycloak Config (Simulating provisioning with config)
        # connect() auto-creates the realm with default config. We update it.
        realm = await client.realms.get()
        
        updated_realm = await client.realms.update(
            description="Testing SDK KC Config", 
            keycloak_config=kc_conf
        )
        
        assert updated_realm.keycloak_config is not None
        assert updated_realm.keycloak_config.server_url == "https://auth.example.com"
        assert updated_realm.keycloak_config.sync_groups is True
        
        # 2. Update Realm Keycloak Config
        new_kc_conf = RealmKeycloakConfig(
            server_url="https://new.example.com",
            keycloak_realm="my-realm",
            client_id="my-client",
            sync_groups=False
        )
        
        # We need the ID from updated_realm or just use realm.id
        updated_realm_2 = await client.realms.update(description="Updated Desc", keycloak_config=new_kc_conf)
        
        assert updated_realm_2.description == "Updated Desc"
        assert updated_realm_2.keycloak_config.server_url == "https://new.example.com"
        assert updated_realm_2.keycloak_config.sync_groups is False
        assert updated_realm_2.keycloak_config.client_id == "my-client" 
        
        # 3. Verify Persistence
        fetched_realm = await client.realms.get()
        assert fetched_realm.keycloak_config.sync_groups is False
        assert fetched_realm.keycloak_config.server_url == "https://new.example.com"
