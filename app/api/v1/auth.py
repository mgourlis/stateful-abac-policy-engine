from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from app.api.deps import get_current_principal, get_db, get_optional_current_principal, AnonymousPrincipal, oauth2_scheme_optional
from common.schemas.auth import (
    CheckAccessRequest, AccessResponse, AccessResponseItem,
    GetPermittedActionsRequest, GetPermittedActionsResponse,
    GetAuthorizationConditionsRequest, AuthorizationConditionsResponse
)
from common.application.auth_service import AuthService
from typing import Union, Optional, List, Dict, Any, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/check-access", response_model=AccessResponse)
async def check_access(
    request: CheckAccessRequest,
    background_tasks: BackgroundTasks,
    token: Optional[str] = Depends(oauth2_scheme_optional),
    db: AsyncSession = Depends(get_db)
):
    
    # Resolve principal
    from app.api.deps import resolve_principal_from_token
    from common.services.audit import log_authorization
    from common.core.database import AsyncSessionLocal
    
    principal = await resolve_principal_from_token(db, token, realm_context=request.realm_name)
    
    service = AuthService(db)
    
    try:
        results, audits = await service.check_access(
            realm_name=request.realm_name,
            principal=principal,
            req_access=request.req_access,
            auth_context=request.auth_context,
            role_names=request.role_names
        )
        
        # Schedule audit logging
        for audit in audits:
            background_tasks.add_task(log_authorization, audit, AsyncSessionLocal)
            
        return AccessResponse(results=results)
        
    except ValueError as e:
        # Catch cache/mapping errors (e.g. unknown realm/role/action)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Internal Authorization Error: {e}")
        raise HTTPException(status_code=500, detail=f"Internal Authorization Error: {e}")


@router.post("/get-permitted-actions", response_model=GetPermittedActionsResponse)
async def get_permitted_actions(
    request: GetPermittedActionsRequest,
    background_tasks: BackgroundTasks,
    token: Optional[str] = Depends(oauth2_scheme_optional),
    db: AsyncSession = Depends(get_db)
):
    """
    Get the list of permitted actions for each resource.
    
    For each resource (or type-level if no external_resource_ids provided),
    returns the list of actions the authenticated principal is allowed to perform.
    """
    from app.api.deps import resolve_principal_from_token
    from common.services.audit import log_authorization
    from common.schemas.auth import GetPermittedActionsItem
    from common.core.database import AsyncSessionLocal
    
    principal = await resolve_principal_from_token(db, token, realm_context=request.realm_name)
    
    service = AuthService(db)
    
    try:
        # Convert request items to schema items
        resources = [
            GetPermittedActionsItem(
                resource_type_name=item.resource_type_name,
                external_resource_ids=item.external_resource_ids
            )
            for item in request.resources
        ]
        
        results, audits = await service.get_permitted_actions(
            realm_name=request.realm_name,
            principal=principal,
            resources=resources,
            auth_context=request.auth_context,
            role_names=request.role_names
        )
        
        # Schedule audit logging
        for audit in audits:
            background_tasks.add_task(log_authorization, audit, AsyncSessionLocal)
            
        return GetPermittedActionsResponse(results=results)
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Internal Authorization Error: {e}")
        raise HTTPException(status_code=500, detail=f"Internal Authorization Error: {e}")


@router.post("/get-authorization-conditions")
async def get_authorization_conditions(
    request: "GetAuthorizationConditionsRequest",
    token: Optional[str] = Depends(oauth2_scheme_optional),
    db: AsyncSession = Depends(get_db)
):
    """
    Get authorization conditions as JSON DSL for client-side query merging.
    
    Returns the conditions that grant access, which can be converted to
    SearchQuery and merged with user queries for single-query authorization.
    
    This enables efficient database queries by combining user filters with
    authorization filters in a single query, rather than the traditional
    two-phase fetch-then-filter approach.
    
    Returns:
        - filter_type: 'granted_all' (blanket access), 'denied_all' (no access),
                       or 'conditions' (conditional access)
        - conditions_dsl: JSON condition DSL compatible with search_query_dsl
        - external_ids: List of specifically granted resource external IDs
        - has_context_refs: Whether conditions reference $context.* or $principal.*
    """
    from app.api.deps import resolve_principal_from_token
    from common.schemas.auth import GetAuthorizationConditionsRequest, AuthorizationConditionsResponse
    
    principal = await resolve_principal_from_token(db, token, realm_context=request.realm_name)
    service = AuthService(db)
    
    try:
        result = await service.get_authorization_conditions(
            realm_name=request.realm_name,
            principal=principal,
            resource_type_name=request.resource_type_name,
            action_name=request.action_name,
            role_names=request.role_names
        )
        return AuthorizationConditionsResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Internal Authorization Error: {e}")
        raise HTTPException(status_code=500, detail=f"Internal Authorization Error: {e}")
