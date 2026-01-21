from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from common.core.database import get_db, AsyncSessionLocal
from common.schemas.realm_api import (
    RealmCreate, RealmUpdate, RealmRead,
    AuthRoleCreate, AuthRoleUpdate, AuthRoleRead,
    PrincipalCreate, PrincipalUpdate, PrincipalRead,
    BatchPrincipalOperation, BatchRoleOperation,
    BatchActionOperation, BatchResourceTypeOperation,
    BatchResourceOperation, BatchACLOperation,
    ActionCreate, ActionUpdate, ActionRead,
    ResourceTypeCreate, ResourceTypeUpdate, ResourceTypeRead,
    ResourceCreate, ResourceUpdate, ResourceRead,
    ACLCreate, ACLUpdate, ACLRead
)

from common.application.realm_service import RealmService
from common.application.role_service import RoleService
from common.application.principal_service import PrincipalService
from common.application.action_service import ActionService
from common.application.resource_type_service import ResourceTypeService
from common.application.resource_service import ResourceService
from common.application.acl_service import ACLService
from common.services.sync_service import SyncService

import logging

logger = logging.getLogger(__name__)

router = APIRouter()

# Helper for background task
async def self_run_sync_task(realm_id: int):
    async with AsyncSessionLocal() as session:
        service = SyncService(session)
        await service.sync_realm(realm_id)

# --- Realm Endpoints ---
@router.post("/realms", response_model=RealmRead)
async def create_realm(realm_in: RealmCreate, background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    service = RealmService(db)
    try:
        realm = await service.create_realm(realm_in)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    
    # Trigger initial sync if configured
    if realm.keycloak_config and realm.keycloak_config.sync_cron:
         background_tasks.add_task(self_run_sync_task, realm.id)
         
    return realm

@router.get("/realms", response_model=List[RealmRead])
async def list_realms(db: AsyncSession = Depends(get_db)):
    """List all realms."""
    service = RealmService(db)
    return await service.list_realms()

@router.get("/realms/{realm_id}", response_model=RealmRead)
async def get_realm(realm_id: int, db: AsyncSession = Depends(get_db)):
    service = RealmService(db)
    realm = await service.get_realm(realm_id)
    if not realm:
        raise HTTPException(status_code=404, detail="Realm not found")
    return realm

@router.get("/realms/name/{name}", response_model=RealmRead)
async def get_realm_by_name(name: str, db: AsyncSession = Depends(get_db)):
    service = RealmService(db)
    realm = await service.get_realm_by_name(name)
    if not realm:
        raise HTTPException(status_code=404, detail="Realm not found")
    return realm

@router.put("/realms/{realm_id}", response_model=RealmRead)
async def update_realm(realm_id: int, realm_in: RealmUpdate, db: AsyncSession = Depends(get_db)):
    service = RealmService(db)
    try:
        realm = await service.update_realm(realm_id, realm_in)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
        
    if not realm:
        raise HTTPException(status_code=404, detail="Realm not found")
    return realm

@router.delete("/realms/{realm_id}")
async def delete_realm(realm_id: int, db: AsyncSession = Depends(get_db)):
    service = RealmService(db)
    success = await service.delete_realm(realm_id)
    if not success:
        raise HTTPException(status_code=404, detail="Realm not found")
    return {"status": "deleted"}

@router.post("/realms/{realm_id}/sync")
async def sync_realm(realm_id: int, background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    service = RealmService(db)
    realm = await service.get_realm(realm_id)
    if not realm:
        raise HTTPException(status_code=404, detail="Realm not found")
    
    background_tasks.add_task(self_run_sync_task, realm_id)
    return {"status": "sync_started"}

# --- Role Endpoints ---
@router.post("/realms/{realm_id}/roles", response_model=AuthRoleRead)
async def create_role(realm_id: int, role_in: AuthRoleCreate, db: AsyncSession = Depends(get_db)):
    service = RoleService(db)
    # Check realm existence? Or let DB constraint handle it, but generic error.
    # Service could check if we want pretty error. using get_realm.
    # For now direct call.
    return await service.create_role(realm_id, role_in)

@router.get("/realms/{realm_id}/roles/{role_id}", response_model=AuthRoleRead)
async def get_role(realm_id: int, role_id: int, db: AsyncSession = Depends(get_db)):
    service = RoleService(db)
    role = await service.get_role(realm_id, role_id)
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    return role

@router.get("/realms/{realm_id}/roles", response_model=List[AuthRoleRead])
async def list_roles(realm_id: int, db: AsyncSession = Depends(get_db)):
    service = RoleService(db)
    return await service.list_roles(realm_id)

@router.put("/realms/{realm_id}/roles/{role_id}", response_model=AuthRoleRead)
async def update_role(realm_id: int, role_id: int, role_update: AuthRoleUpdate, db: AsyncSession = Depends(get_db)):
    service = RoleService(db)
    role = await service.update_role(realm_id, role_id, role_update)
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    return role

@router.delete("/realms/{realm_id}/roles/{role_id}")
async def delete_role(realm_id: int, role_id: int, db: AsyncSession = Depends(get_db)):
    service = RoleService(db)
    success = await service.delete_role(realm_id, role_id)
    if not success:
        raise HTTPException(status_code=404, detail="Role not found")
    return {"status": "deleted"}

# --- Principal Endpoints ---
@router.post("/realms/{realm_id}/principals", response_model=PrincipalRead)
async def create_principal(realm_id: int, principal_in: PrincipalCreate, db: AsyncSession = Depends(get_db)):
    service = PrincipalService(db)
    try:
        return await service.create_principal(realm_id, principal_in)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/realms/{realm_id}/principals/{principal_id}", response_model=PrincipalRead)
async def get_principal(realm_id: int, principal_id: int, db: AsyncSession = Depends(get_db)):
    service = PrincipalService(db)
    principal = await service.get_principal(realm_id, principal_id)
    if not principal:
        raise HTTPException(status_code=404, detail="Principal not found")
    return principal

@router.get("/realms/{realm_id}/principals", response_model=List[PrincipalRead])
async def list_principals(realm_id: int, db: AsyncSession = Depends(get_db)):
    service = PrincipalService(db)
    return await service.list_principals(realm_id)

@router.put("/realms/{realm_id}/principals/{principal_id}", response_model=PrincipalRead)
async def update_principal(realm_id: int, principal_id: int, principal_update: PrincipalUpdate, db: AsyncSession = Depends(get_db)):
    service = PrincipalService(db)
    try:
        principal = await service.update_principal(realm_id, principal_id, principal_update)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not principal:
        raise HTTPException(status_code=404, detail="Principal not found")
    return principal

@router.delete("/realms/{realm_id}/principals/{principal_id}")
async def delete_principal(realm_id: int, principal_id: int, db: AsyncSession = Depends(get_db)):
    service = PrincipalService(db)
    success = await service.delete_principal(realm_id, principal_id)
    if not success:
        raise HTTPException(status_code=404, detail="Principal not found")
    return {"status": "deleted"}

# --- Action Endpoints ---
@router.post("/realms/{realm_id}/actions", response_model=ActionRead)
async def create_action(realm_id: int, action: ActionCreate, db: AsyncSession = Depends(get_db)):
    service = ActionService(db)
    return await service.create_action(realm_id, action)

@router.get("/realms/{realm_id}/actions", response_model=List[ActionRead])
async def list_actions(realm_id: int, skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db)):
    service = ActionService(db)
    return await service.list_actions(realm_id, skip, limit)

@router.get("/realms/{realm_id}/actions/{action_id}", response_model=ActionRead)
async def get_action(realm_id: int, action_id: int, db: AsyncSession = Depends(get_db)):
    service = ActionService(db)
    obj = await service.get_action(realm_id, action_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Action not found")
    return obj

@router.put("/realms/{realm_id}/actions/{action_id}", response_model=ActionRead)
async def update_action(realm_id: int, action_id: int, action: ActionUpdate, db: AsyncSession = Depends(get_db)):
    service = ActionService(db)
    obj = await service.update_action(realm_id, action_id, action)
    if not obj:
        raise HTTPException(status_code=404, detail="Action not found")
    return obj

@router.delete("/realms/{realm_id}/actions/{action_id}")
async def delete_action(realm_id: int, action_id: int, db: AsyncSession = Depends(get_db)):
    service = ActionService(db)
    success = await service.delete_action(realm_id, action_id)
    if not success:
        raise HTTPException(status_code=404, detail="Action not found")
    return {"status": "deleted"}

# --- ResourceType Endpoints ---
@router.post("/realms/{realm_id}/resource-types", response_model=ResourceTypeRead)
async def create_resource_type(realm_id: int, rt: ResourceTypeCreate, db: AsyncSession = Depends(get_db)):
    service = ResourceTypeService(db)
    return await service.create_resource_type(realm_id, rt)

@router.get("/realms/{realm_id}/resource-types", response_model=List[ResourceTypeRead])
async def list_resource_types(realm_id: int, skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db)):
    service = ResourceTypeService(db)
    return await service.list_resource_types(realm_id, skip, limit)

@router.get("/realms/{realm_id}/resource-types/{rt_id}", response_model=ResourceTypeRead)
async def get_resource_type(realm_id: int, rt_id: int, db: AsyncSession = Depends(get_db)):
    service = ResourceTypeService(db)
    obj = await service.get_resource_type(realm_id, rt_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Resource Type not found")
    return obj

@router.put("/realms/{realm_id}/resource-types/{rt_id}", response_model=ResourceTypeRead)
async def update_resource_type(realm_id: int, rt_id: int, rt: ResourceTypeUpdate, db: AsyncSession = Depends(get_db)):
    service = ResourceTypeService(db)
    obj = await service.update_resource_type(realm_id, rt_id, rt)
    if not obj:
        raise HTTPException(status_code=404, detail="Resource Type not found")
    return obj

@router.delete("/realms/{realm_id}/resource-types/{rt_id}")
async def delete_resource_type(realm_id: int, rt_id: int, db: AsyncSession = Depends(get_db)):
    service = ResourceTypeService(db)
    success = await service.delete_resource_type(realm_id, rt_id)
    if not success:
        raise HTTPException(status_code=404, detail="Resource Type not found")
    return {"status": "deleted"}

# --- Resource Endpoints ---
@router.post("/realms/{realm_id}/resources", response_model=ResourceRead)
async def create_resource(realm_id: int, resource_in: ResourceCreate, db: AsyncSession = Depends(get_db)):
    service = ResourceService(db)
    try:
        return await service.create_resource(realm_id, resource_in)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/realms/{realm_id}/resources")
async def list_resources(
    realm_id: int,
    skip: int = 0,
    limit: int = 50,
    resource_type_id: Optional[int] = None,
    external_id: Optional[str] = None,
    attributes: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """
    List resources with optional pagination and filters.
    
    - skip/limit: Pagination (default 50 per page)
    - resource_type_id: Filter by resource type
    - external_id: Partial match on external ID
    - attributes: JSON string of attribute filters, e.g. {"name": "value"}
    """
    service = ResourceService(db)
    
    # Parse attributes filter from JSON string
    attrs_filter = None
    if attributes:
        import json
        try:
            attrs_filter = json.loads(attributes)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid attributes JSON")
    
    items, total = await service.search_resources(
        realm_id,
        skip=skip,
        limit=limit,
        resource_type_id=resource_type_id,
        external_id=external_id,
        attributes_filter=attrs_filter
    )
    
    return {
        "items": items,
        "total": total,
        "skip": skip,
        "limit": limit,
        "has_more": (skip + len(items)) < total
    }

@router.get("/realms/{realm_id}/resources/all", response_model=List[ResourceRead])
async def list_all_resources(realm_id: int, db: AsyncSession = Depends(get_db)):
    """
    List all resources without pagination.
    
    For SDK backward compatibility - use /resources with pagination for large datasets.
    """
    service = ResourceService(db)
    return await service.list_resources(realm_id)

@router.get("/realms/{realm_id}/resources/{resource_id}", response_model=ResourceRead)
async def get_resource(realm_id: int, resource_id: int, db: AsyncSession = Depends(get_db)):
    service = ResourceService(db)
    obj = await service.get_resource(realm_id, resource_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Resource not found")
    return obj

@router.put("/realms/{realm_id}/resources/{resource_id}", response_model=ResourceRead)
async def update_resource(realm_id: int, resource_id: int, resource_in: ResourceUpdate, db: AsyncSession = Depends(get_db)):
    service = ResourceService(db)
    try:
        obj = await service.update_resource(realm_id, resource_id, resource_in)
    except ValueError as e:
         raise HTTPException(status_code=400, detail=str(e))
         
    if not obj:
        raise HTTPException(status_code=404, detail="Resource not found")
    return obj

@router.delete("/realms/{realm_id}/resources/{resource_id}")
async def delete_resource(realm_id: int, resource_id: int, db: AsyncSession = Depends(get_db)):
    service = ResourceService(db)
    success = await service.delete_resource(realm_id, resource_id)
    if not success:
        raise HTTPException(status_code=404, detail="Resource not found")
    return {"status": "deleted"}

# --- External ID Resource Endpoints ---
@router.get("/realms/{realm_id}/resources/external/{type_id_or_name}/{external_id}", response_model=ResourceRead)
async def get_resource_by_external_id(realm_id: int, type_id_or_name: str, external_id: str, db: AsyncSession = Depends(get_db)):
    service = ResourceService(db)
    obj = await service.get_resource_by_external_id(realm_id, type_id_or_name, external_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Resource not found")
    return obj

@router.put("/realms/{realm_id}/resources/external/{type_id_or_name}/{external_id}", response_model=ResourceRead)
async def update_resource_by_external_id(
    realm_id: int, 
    type_id_or_name: str,
    external_id: str, 
    resource_in: ResourceUpdate, 
    db: AsyncSession = Depends(get_db)
):
    service = ResourceService(db)
    # Helper to resolve and update
    # Need to reimplement the logic here or add to service?
    # Added resolve logic to service logic already? 
    # Actually I didn't add update_resource_by_external_id to service.
    # I can fetch ID and call update.
    
    # 1. Resolve ID using service helper (private or make public)?
    # I'll just use get_resource_by_external_id to get ID, then update.
    
    obj_read = await service.get_resource_by_external_id(realm_id, type_id_or_name, external_id)
    if not obj_read:
        raise HTTPException(status_code=404, detail="Resource not found")
    
    return await service.update_resource(realm_id, obj_read.id, resource_in)

@router.delete("/realms/{realm_id}/resources/external/{type_id_or_name}/{external_id}")
async def delete_resource_by_external_id(realm_id: int, type_id_or_name: str, external_id: str, db: AsyncSession = Depends(get_db)):
    service = ResourceService(db)
    obj_read = await service.get_resource_by_external_id(realm_id, type_id_or_name, external_id)
    if not obj_read:
        raise HTTPException(status_code=404, detail="Resource not found")
        
    await service.delete_resource(realm_id, obj_read.id)
    return {"status": "deleted"}


# --- ACL Endpoints ---
@router.post("/realms/{realm_id}/acls", response_model=ACLRead)
async def create_acl(realm_id: int, acl: ACLCreate, db: AsyncSession = Depends(get_db)):
    service = ACLService(db)
    try:
        return await service.create_acl(realm_id, acl)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) # not found for external id

@router.get("/realms/{realm_id}/acls")
async def list_acls(
    realm_id: int, 
    skip: int = 0, 
    limit: int = 100, 
    resource_type_id: Optional[int] = None,
    action_id: Optional[int] = None,
    principal_id: Optional[int] = None,
    role_id: Optional[int] = None,
    resource_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db)
):
    service = ACLService(db)
    filters = {
        "resource_type_id": resource_type_id,
        "action_id": action_id,
        "principal_id": principal_id,
        "role_id": role_id,
        "resource_id": resource_id
    }
    items, total = await service.list_acls(realm_id, skip, limit, filters)
    return {
        "items": items,
        "total": total,
        "skip": skip,
        "limit": limit,
        "has_more": (skip + len(items)) < total
    }

@router.get("/realms/{realm_id}/acls/all", response_model=List[ACLRead])
async def list_all_acls(
    realm_id: int, 
    resource_type_id: Optional[int] = None,
    action_id: Optional[int] = None,
    principal_id: Optional[int] = None,
    role_id: Optional[int] = None,
    resource_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db)
):
    service = ACLService(db)
    filters = {
        "resource_type_id": resource_type_id,
        "action_id": action_id,
        "principal_id": principal_id,
        "role_id": role_id,
        "resource_id": resource_id
    }
    return await service.list_all_acls(realm_id, filters)

@router.get("/realms/{realm_id}/acls/{acl_id}", response_model=ACLRead)
async def get_acl(realm_id: int, acl_id: int, db: AsyncSession = Depends(get_db)):
    service = ACLService(db)
    obj = await service.get_acl(realm_id, acl_id)
    if not obj:
        raise HTTPException(status_code=404, detail="ACL not found")
    return obj

@router.put("/realms/{realm_id}/acls/{acl_id}", response_model=ACLRead)
async def update_acl(realm_id: int, acl_id: int, acl: ACLUpdate, db: AsyncSession = Depends(get_db)):
    service = ACLService(db)
    obj = await service.update_acl(realm_id, acl_id, acl)
    if not obj:
        raise HTTPException(status_code=404, detail="ACL not found")
    return obj

@router.delete("/realms/{realm_id}/acls/{acl_id}")
async def delete_acl(realm_id: int, acl_id: int, db: AsyncSession = Depends(get_db)):
    service = ACLService(db)
    success = await service.delete_acl(realm_id, acl_id)
    if not success:
           raise HTTPException(status_code=404, detail="ACL not found")
    return {"status": "deleted"}

# --- Batch Operations ---
@router.post("/realms/{realm_id}/principals/batch", response_model=BatchPrincipalOperation)
async def batch_principals(realm_id: int, operation: BatchPrincipalOperation, db: AsyncSession = Depends(get_db)):
    service = PrincipalService(db)
    return await service.batch_principals(realm_id, operation)

@router.post("/realms/{realm_id}/roles/batch", response_model=BatchRoleOperation)
async def batch_roles(realm_id: int, operation: BatchRoleOperation, db: AsyncSession = Depends(get_db)):
    service = RoleService(db)
    return await service.batch_roles(realm_id, operation)

@router.post("/realms/{realm_id}/actions/batch", response_model=BatchActionOperation)
async def batch_actions(realm_id: int, operation: BatchActionOperation, db: AsyncSession = Depends(get_db)):
    service = ActionService(db)
    return await service.batch_actions(realm_id, operation)

@router.post("/realms/{realm_id}/resource-types/batch", response_model=BatchResourceTypeOperation)
async def batch_resource_types(realm_id: int, operation: BatchResourceTypeOperation, db: AsyncSession = Depends(get_db)):
    service = ResourceTypeService(db)
    return await service.batch_resource_types(realm_id, operation)

@router.post("/realms/{realm_id}/resources/batch", response_model=BatchResourceOperation)
async def batch_resources(realm_id: int, operation: BatchResourceOperation, db: AsyncSession = Depends(get_db)):
    service = ResourceService(db)
    return await service.batch_resources(realm_id, operation)

@router.post("/realms/{realm_id}/acls/batch", response_model=BatchACLOperation)
async def batch_acls(realm_id: int, operation: BatchACLOperation, db: AsyncSession = Depends(get_db)):
    service = ACLService(db)
    try:
        return await service.batch_acls(realm_id, operation)
    except ValueError as e:
         raise HTTPException(status_code=404, detail=str(e))
