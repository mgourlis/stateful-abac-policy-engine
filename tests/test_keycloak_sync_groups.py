import pytest
from unittest.mock import MagicMock, patch
from sqlalchemy import select, text
from sqlalchemy.orm import selectinload
from common.models import Realm, RealmKeycloakConfig, AuthRole, Principal
from common.services.sync_service import SyncService

@pytest.mark.asyncio
async def test_sync_groups_feature(session):
    import uuid
    # 1. Setup Realm with sync_groups=True
    r_name = f"SyncGroupRealm_{uuid.uuid4()}"
    realm = Realm(name=r_name)
    session.add(realm)
    await session.commit()
    await session.refresh(realm)
    
    try:
        config = RealmKeycloakConfig(
            realm_id=realm.id,
            server_url="http://mock",
            keycloak_realm="mock_realm",
            client_id="mock_client",
            sync_groups=True
        )
        session.add(config)
        await session.commit()
        
        # 2. Mock Keycloak Adapter
        with patch("common.services.sync_service.KeycloakAdapter") as MockAdapter:
            # Instance mock
            adapter_instance = MockAdapter.return_value
            
            # Mock Data
            mock_roles = [{'name': 'Role_Admin', 'attributes': {'type': 'role'}}]
            mock_groups = [{'name': 'Group_Devs', 'path': '/Devs', 'attributes': {'type': 'group'}}]
            mock_users = [{'username': 'user1', 'id': 'u1', 'attributes': {}}]
            
            mock_user_roles = [{'name': 'Role_Admin'}]
            mock_user_groups = [{'name': 'Group_Devs'}]
            
            # Setup returns
            adapter_instance.get_roles.return_value = mock_roles
            adapter_instance.get_groups.return_value = mock_groups
            adapter_instance.get_principals.return_value = mock_users
            adapter_instance.get_user_roles.return_value = mock_user_roles
            adapter_instance.get_user_groups.return_value = mock_user_groups
            
            # 3. Run Sync
            service = SyncService(session)
            await service.sync_realm(realm.id)
            
            # 4. Verify Roles Created
            stmt = select(AuthRole).where(AuthRole.realm_id == realm.id)
            result = await session.execute(stmt)
            roles = {r.name: r for r in result.scalars().all()}
            
            assert 'Role_Admin' in roles, "Standard Role should be synced"
            assert 'Group_Devs' in roles, "Group should be synced as Role"
            assert roles['Group_Devs'].attributes['type'] == 'group', "Group attributes should be preserved"
            
            # 5. Verify User Roles Assignment
            stmt = select(Principal).options(selectinload(Principal.roles)).where(Principal.realm_id == realm.id, Principal.username == 'user1')
            result = await session.execute(stmt)
            user = result.scalar_one()
            
            user_role_names = {r.name for r in user.roles}
            assert 'Role_Admin' in user_role_names, "Direct Role assignment missing"
            assert 'Group_Devs' in user_role_names, "Group Role assignment missing"

            # 6. Verify disable sync_groups
            config.sync_groups = False
            await session.commit()
            
            # Reset Mock calls to ensure we check what is called
            adapter_instance.reset_mock()
            adapter_instance.get_roles.return_value = mock_roles
            adapter_instance.get_principals.return_value = mock_users
            adapter_instance.get_user_roles.return_value = mock_user_roles
            
            await service.sync_realm(realm.id)
            
            # Should NOT call get_groups or get_user_groups
            adapter_instance.get_groups.assert_not_called()
            # get_user_groups should not be called either
            # We need to verify that. Note: get_user_groups is called inside loop over users.
            # But we mock it.
            adapter_instance.get_user_groups.assert_not_called()

    finally:
        # Clean up
        # We need to use text() for raw SQL queries
        await session.execute(text("DELETE FROM principal_roles USING principal WHERE principal_roles.principal_id = principal.id AND principal.realm_id = :rid"), {"rid": realm.id})
        await session.execute(text("DELETE FROM principal WHERE realm_id = :rid"), {"rid": realm.id})
        await session.execute(text("DELETE FROM auth_role WHERE realm_id = :rid"), {"rid": realm.id})
        await session.execute(text("DELETE FROM realm_keycloak_config WHERE realm_id = :rid"), {"rid": realm.id})
        await session.execute(text("DELETE FROM realm WHERE id = :rid"), {"rid": realm.id})
        await session.commit()
