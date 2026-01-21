"""
DB Manager for Authorization checks.
This delegates to the shared AuthService, mimicking the HTTP API flow.
"""
from typing import List, Dict, Any, Optional, Union, TYPE_CHECKING
import logging
import asyncio

from .base import DBBaseManager
from common.models import Principal
from common.services.security import AnonymousPrincipal
from common.application.auth_service import AuthService
from common.services.security import resolve_principal_from_token
from common.schemas.auth import AccessRequestItem, GetPermittedActionsItem as SchemaGetPermittedActionsItem
from ..models import (
    CheckAccessItem, AccessResponse, AccessResponseItem,
    GetPermittedActionsItem, GetPermittedActionsResponse, PermittedActionsResponseItem
)
from ..interfaces import IAuthManager

if TYPE_CHECKING:
    from ..clients.db import DBStatefulABACClient

logger = logging.getLogger(__name__)


class DBAuthManager(DBBaseManager, IAuthManager):
    """
    DB-mode manager for high-performance authorization checks.
    
    This mimics the HTTP API flow:
    1. Resolves principal from JWT token (like app/api/v1/auth.py)
    2. Delegates to AuthService (same as HTTP endpoint)
    
    Bypasses HTTP overhead for maximum performance while maintaining
    identical behavior to the API endpoint.
    """
    
    def __init__(self, db_session: Any, client: Optional["DBStatefulABACClient"] = None):
        """
        Initialize the DB Auth Manager.
        
        Args:
            db_session: The database session factory.
            client: Reference to parent DBStatefulABACClient (for token access).
        """
        super().__init__(db_session, client)
    
    async def check_access(
        self, 
        resources: List[CheckAccessItem],
        auth_context: Optional[Dict[str, Any]] = None,
        role_names: Optional[List[str]] = None,
        chunk_size: Optional[int] = None,
        max_concurrent: Optional[int] = None
    ) -> AccessResponse:
        """
        Check access for a list of resources.
        
        This mimics the exact flow of the HTTP /check-access endpoint:
        1. Resolve principal from token using resolve_principal_from_token()
        2. Call AuthService.check_access() with the resolved principal
        
        Args:
            resources: List of CheckAccessItem objects to check.
            auth_context: Optional context dictionary (merged into context).
            role_names: Optional list of role names to check against (RBAC filter).
            chunk_size: Not used in DB mode, kept for signature compatibility.
            max_concurrent: Not used in DB mode, kept for signature compatibility.
            
        Returns:
            AccessResponse with results for each resource type/action pair.
        """
        realm_name = str(self.client.realm) # Default to client realm
        async with self._db_session.get_session() as session:
            # Get token from client (mimics HTTP flow where token comes from header)
            token = None
            if self._client:
                token = getattr(self._client, 'token', None)
            
            # Resolve principal from token - EXACTLY like app/api/v1/auth.py does
            # Uses common/services/security.resolve_principal_from_token
            principal = await resolve_principal_from_token(
                db=session,
                token=token,
                realm_context=realm_name
            )
            
            # Convert SDK CheckAccessItem to schema AccessRequestItem
            req_access = []
            for item in resources:
                if isinstance(item, dict):
                    # Handle dict input
                    res_ids = item.get("external_resource_ids")
                    if res_ids is None and item.get("resource_id"):
                        rid = item.get("resource_id")
                        res_ids = [rid] if isinstance(rid, str) else rid # Assuming list if not str
                    
                    req_access.append(AccessRequestItem(
                        resource_type_name=item.get("resource_type_name"),
                        action_name=item.get("action_name"),
                        external_resource_ids=res_ids,
                        return_type=item.get("return_type", "id_list")
                    ))
                else:
                    # Handle object input (CheckAccessItem)
                    req_access.append(AccessRequestItem(
                        resource_type_name=item.resource_type_name,
                        action_name=item.action_name,
                        external_resource_ids=item.external_resource_ids,
                        return_type=item.return_type or "id_list"
                    ))
            
            # Call the shared AuthService - EXACTLY like app/api/v1/auth.py does
            service = AuthService(session)
            results, audits = await service.check_access(
                realm_name=realm_name,
                principal=principal,
                req_access=req_access,
                auth_context=auth_context,
                role_names=role_names
            )
            
            # Fire-and-forget audit logging (like FastAPI background_tasks)
            from common.services.audit import log_authorization
            for audit in audits:
                asyncio.create_task(log_authorization(audit))
            
            # Map service results to SDK AccessResponseItem
            sdk_results = [
                AccessResponseItem(
                    resource_type_name=r.resource_type_name,
                    action_name=r.action_name,
                    answer=r.answer
                )
                for r in results
            ]
            
            return AccessResponse(results=sdk_results)

    async def get_permitted_actions(
        self,
        resources: List[GetPermittedActionsItem],
        auth_context: Optional[Dict[str, Any]] = None,
        role_names: Optional[List[str]] = None
    ) -> GetPermittedActionsResponse:
        """
        Get the list of permitted actions for each resource.
        
        Args:
            resources: List of GetPermittedActionsItem objects.
            auth_context: Optional context dictionary for condition evaluation.
            role_names: Optional list of role names to check against.
            
        Returns:
            GetPermittedActionsResponse with actions permitted per resource.
        """
        realm_name = str(self.client.realm)
        async with self._db_session.get_session() as session:
            # Get token from client
            token = None
            if self._client:
                token = getattr(self._client, 'token', None)
            
            # Resolve principal from token
            principal = await resolve_principal_from_token(
                db=session,
                token=token,
                realm_context=realm_name
            )
            
            # Convert SDK items to schema items
            schema_resources = [
                SchemaGetPermittedActionsItem(
                    resource_type_name=item.resource_type_name,
                    external_resource_ids=item.external_resource_ids
                )
                for item in resources
            ]
            
            # Call AuthService
            service = AuthService(session)
            results, audits = await service.get_permitted_actions(
                realm_name=realm_name,
                principal=principal,
                resources=schema_resources,
                auth_context=auth_context,
                role_names=role_names
            )
            
            # Fire-and-forget audit logging
            from common.services.audit import log_authorization
            for audit in audits:
                asyncio.create_task(log_authorization(audit))
            
            # Map service results to SDK response items
            sdk_results = [
                PermittedActionsResponseItem(
                    resource_type_name=r.resource_type_name,
                    external_resource_id=r.external_resource_id,
                    actions=r.actions
                )
                for r in results
            ]
            
            return GetPermittedActionsResponse(results=sdk_results)
