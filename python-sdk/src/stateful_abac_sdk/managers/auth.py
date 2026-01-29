import asyncio
from typing import List, Dict, Any, Union, Optional, Tuple
from pydantic import BaseModel
from .base import BaseManager
from ..interfaces import IAuthManager

from ..models import (
    CheckAccessItem, AccessResponse, AccessResponseItem,
    GetPermittedActionsItem, GetPermittedActionsResponse, PermittedActionsResponseItem
)


class AuthManager(BaseManager, IAuthManager):
    """Manager for authorization checks."""
    
    CHUNK_SIZE: int = 5000  # Max items per request
    MAX_CONCURRENT: int = 10  # Max parallel requests
    
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
        
        Automatically splits large requests into parallel chunks for optimal performance.
        Batches by total number of external_resource_ids, not just number of items.
        
        Args:
            resources: List of CheckAccessItem objects.
            auth_context: Optional context dictionary.
            role_names: Optional list of roles to check against (RBAC override).
            chunk_size: Optional override for chunk size (default: 5000).
            max_concurrent: Optional override for max concurrent requests (default: 10).

        Returns:
            AccessResponse object containing results.
        """
        realm_name = str(self.client.realm) # Default to client realm
        
        chunk_size = chunk_size or self.CHUNK_SIZE
        max_concurrent = max_concurrent or self.MAX_CONCURRENT
        
        # Track original type of external_resource_ids for each item
        # Key: (resource_type_name, action_name) -> bool (True if original was int)
        original_types: Dict[Tuple[str, str], bool] = {}
        for r in resources:
            if r.external_resource_ids and len(r.external_resource_ids) > 0:
                is_int_type = isinstance(r.external_resource_ids[0], int)
                original_types[(r.resource_type_name, r.action_name)] = is_int_type
        
        # Calculate total number of IDs across all items
        total_ids = sum(
            len(r.external_resource_ids) if r.external_resource_ids else 0 
            for r in resources
        )
        
        # Single request if within chunk size
        if total_ids <= chunk_size:
            return await self._single_check_access(
                realm_name, resources, auth_context, role_names, original_types
            )
        
        # Split resources into chunks based on total IDs
        chunks: List[List[CheckAccessItem]] = []
        current_chunk: List[CheckAccessItem] = []
        current_chunk_size = 0
        
        for resource in resources:
            resource_ids = resource.external_resource_ids or []
            
            if not resource_ids:
                # No IDs, add to current chunk as-is (global check)
                current_chunk.append(resource)
                continue
            
            # If this single resource has more IDs than chunk_size, split it
            if len(resource_ids) > chunk_size:
                # Flush current chunk first if not empty
                if current_chunk:
                    chunks.append(current_chunk)
                    current_chunk = []
                    current_chunk_size = 0
                
                # Split this resource's IDs into multiple chunks
                for i in range(0, len(resource_ids), chunk_size):
                    id_slice = resource_ids[i:i + chunk_size]
                    split_item = CheckAccessItem(
                        resource_type_name=resource.resource_type_name,
                        action_name=resource.action_name,
                        external_resource_ids=id_slice,
                        return_type=resource.return_type
                    )
                    chunks.append([split_item])
            else:
                # Check if adding this resource would exceed chunk size
                if current_chunk_size + len(resource_ids) > chunk_size:
                    # Start a new chunk
                    if current_chunk:
                        chunks.append(current_chunk)
                    current_chunk = [resource]
                    current_chunk_size = len(resource_ids)
                else:
                    current_chunk.append(resource)
                    current_chunk_size += len(resource_ids)
        
        # Don't forget the last chunk
        if current_chunk:
            chunks.append(current_chunk)
        
        # Semaphore to limit concurrent requests
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def limited_request(chunk: List[CheckAccessItem]) -> AccessResponse:
            async with semaphore:
                return await self._single_check_access(
                    realm_name, chunk, auth_context, role_names, original_types
                )
        
        # Fire all chunk requests in parallel (with concurrency limit)
        responses = await asyncio.gather(*[
            limited_request(chunk) for chunk in chunks
        ])
        
        # Merge results - combine answers for the same (resource_type, action) pair
        merged: Dict[Tuple[str, str], AccessResponseItem] = {}
        
        for response in responses:
            for item in response.results:
                key = (item.resource_type_name, item.action_name)
                
                if key not in merged:
                    # First occurrence - just store it
                    merged[key] = item
                else:
                    # Merge answers
                    existing = merged[key]
                    if isinstance(existing.answer, list) and isinstance(item.answer, list):
                        # Combine lists
                        existing.answer = existing.answer + item.answer
                    elif isinstance(existing.answer, bool) and isinstance(item.answer, bool):
                        # For decisions, AND them together (all must be True for True)
                        existing.answer = existing.answer and item.answer
        
        return AccessResponse(results=list(merged.values()))
    
    async def _single_check_access(
        self,
        realm_name: str,
        resources: List[CheckAccessItem],
        auth_context: Optional[Dict[str, Any]],
        role_names: Optional[List[str]],
        original_types: Dict[Tuple[str, str], bool]
    ) -> AccessResponse:
        """Execute a single check-access request with type casting."""
        payload = {
            "realm_name": realm_name,
            "req_access": [r.model_dump(exclude_unset=True) for r in resources],
            "auth_context": auth_context or {},
            "role_names": role_names
        }
        
        response = await self._post("/check-access", json=payload)
        access_response = AccessResponse(**response)
        
        # Cast response answers back to original type if needed
        for result in access_response.results:
            key = (result.resource_type_name, result.action_name)
            if key in original_types and original_types[key]:
                # Original was int, cast answer back to int if it's a list
                if isinstance(result.answer, list):
                    result.answer = [int(x) for x in result.answer]
        
        return access_response

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
        
        payload = {
            "realm_name": realm_name,
            "resources": [r.model_dump(exclude_unset=True) for r in resources],
            "auth_context": auth_context or {},
            "role_names": role_names
        }
        
        response = await self._post("/get-permitted-actions", json=payload)
        return GetPermittedActionsResponse(**response)

    async def get_authorization_conditions(
        self,
        resource_type_name: str,
        action_name: str,
        role_names: Optional[List[str]] = None
    ) -> "AuthorizationConditionsResponse":
        """
        Get authorization conditions as JSON DSL for SearchQuery conversion.
        
        This enables single-query authorization: the returned conditions can be
        converted to a SearchQuery using ABACConditionConverter and merged with
        user queries using SearchQuery.merge() for optimal database performance.
        
        Args:
            resource_type_name: Name of the resource type.
            action_name: Action being performed (e.g., "read", "update").
            role_names: Optional list of role names to check against.
            
        Returns:
            AuthorizationConditionsResponse with:
                - filter_type: 'granted_all', 'denied_all', or 'conditions'
                - conditions_dsl: JSON condition DSL compatible with search_query_dsl
                - external_ids: List of specifically granted resource external IDs
                - has_context_refs: Whether conditions reference $context.* or $principal.*
        """
        from ..models import AuthorizationConditionsResponse
        
        realm_name = str(self.client.realm)
        
        payload = {
            "realm_name": realm_name,
            "resource_type_name": resource_type_name,
            "action_name": action_name,
            "role_names": role_names
        }
        
        response = await self._post("/get-authorization-conditions", json=payload)
        return AuthorizationConditionsResponse(**response)
