import pytest
import uuid
import sys
import os
from httpx import ASGITransport, AsyncClient
from app.main import app
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from jose import jwt

# Add SDK path
sdk_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../python-sdk/src"))
if sdk_path not in sys.path:
    sys.path.insert(0, sdk_path)

from stateful_abac_sdk import StatefulABACClient
from stateful_abac_sdk.models import RealmKeycloakConfig

@pytest.fixture
def sdk_client():
    transport = ASGITransport(app=app)
    return StatefulABACClient("http://test/api/v1", realm="test_realm", transport=transport)

@pytest.mark.asyncio
async def test_multi_realm_auth_flow(session):
    # 1. Generate RSA Key Pair
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )
    public_key = private_key.public_key()
    
    # Serialize Public Key to PEM format
    pem_public = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode('utf-8')
    
    # Serialize Private Key to PEM for signing
    pem_private = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption()
    )

    # 2. Configure Realm
    unique_realm_name = f"RSA_{uuid.uuid4()}"
    transport = ASGITransport(app=app)
    client = StatefulABACClient("http://test/api/v1", realm=unique_realm_name, transport=transport)

    async with client.connect(token=None):
        kc_conf = RealmKeycloakConfig(
            server_url="https://auth.example.com",
            keycloak_realm="rsa-realm",
            client_id="my-client",
            public_key=pem_public,
            algorithm="RS256"
        )
        
        # Realm created with config automatically if not exists
        # Update it to set config if it does?
        # Manually calling update since create no longer accepts args like this in my previous assumption?
        # Wait, create() takes keycloak_config.
        # But create is called auto on connect.
        # So I should pass None to connect for safety?
        # Logic: connect() -> _resolve -> Not Found -> create(realm=name, default props).
        # It doesn't pass my kc_conf.
        # So I must update it after connect.
        
        realm = await client.realms.get()
        
        # Update with KC config
        await client.realms.update(description="Realm for RSA Test", keycloak_config=kc_conf)
        
        # Setup basic Access Control
        rt = await client.resource_types.create("file", False)
        act = await client.actions.create("read")
        
        # Create Principal (User)
        user = await client.principals.create("alice")
        
        # Create ACL for alice
        await client.acls.create(
                 resource_type_id=rt.id, 
                 action_id=act.id,
                 principal_id=user.id
        )
        
        # Create a resource so we can match it
        res_obj = await client.resources.create(rt.id, external_id="ext-file-1", attributes={"name": "test-file"})
        
        # DEBUG: Verify Realm Exists in DB
        from common.models import Realm
        from sqlalchemy import select
        res = await session.execute(select(Realm).where(Realm.name == unique_realm_name))
        r = res.scalars().first()
        assert r is not None, f"Realm {unique_realm_name} NOT found in DB!"
        print(f"DEBUG: Found Realm {r.name} with ID {r.id}")
        
    # 3. Create Token
    token_payload = {
        "sub": "alice", # Matches principal.username because it's a string
        "realm": unique_realm_name,
        "iss": "https://auth.example.com/realms/rsa-realm",
        "exp": 9999999999,
        "iat": 0
    }
    
    # Encode with RSA private key
    encoded_token = jwt.encode(token_payload, pem_private, algorithm="RS256")
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        req_body = {
            "realm_name": unique_realm_name,
            "req_access": [
                {
                    "resource_type_name": "file",
                    "action_name": "read"
                }
            ]
        }
        
        headers = {"Authorization": f"Bearer {encoded_token}"}
        resp = await ac.post("/api/v1/check-access", json=req_body, headers=headers)
        
        assert resp.status_code == 200, resp.text
        data = resp.json()
        # Should return list of authorized resource IDs. Since we created 1 and have wildcard, should be [id]
        assert len(data['results'][0]['answer']) > 0, "Alice should have access to the resource"
        assert "ext-file-1" in data['results'][0]['answer'], "Alice should see the specific resource"
        
        # 5. Verify Invalid Signature Fails
        # Create valid token with WRONG key
        other_private = rsa.generate_private_key(65537, 2048)
        pem_other = other_private.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption()
        )
        bad_token = jwt.encode(token_payload, pem_other, algorithm="RS256")
        
        headers_bad = {"Authorization": f"Bearer {bad_token}"}
        # Reuse URL that worked
        url = str(resp.request.url.path)
        resp_bad = await ac.post(url, json=req_body, headers=headers_bad)
        
        assert resp_bad.status_code == 200, resp_bad.text
        data_bad = resp_bad.json()
        assert data_bad['results'][0]['answer'] == [], "Anonymous should be denied (empty list)" # Anonymous denied
