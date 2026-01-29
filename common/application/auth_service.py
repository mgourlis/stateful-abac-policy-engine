from typing import List, Dict, Tuple, Any, Optional, Union
import asyncio
import json
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, bindparam, select

from common.models import Principal, PrincipalRoles
from common.services.security import AnonymousPrincipal
from common.services.cache import CacheService
from common.services.context_builder import build_unified_context
from common.services.audit import AuditEntry
from common.core.database import AsyncSessionLocal
from common.schemas.auth import (
    CheckAccessRequest, AccessResponseItem, AccessRequestItem,
    GetPermittedActionsItem, PermittedActionsResponseItem
)

class AuthService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def check_access(
        self,
        realm_name: str,
        principal: Union[Principal, AnonymousPrincipal],
        req_access: List[Any], # List of request items
        auth_context: Dict[str, Any] = None,
        role_names: List[str] = None
    ) -> Tuple[List[AccessResponseItem], List[AuditEntry]]:
        """
        Main entry point for checking access.
        Returns a tuple of (results, audit_entries).
        """
        
        # Get Realm Map (cached)
        realm_map = await CacheService.get_realm_map(realm_name, db_session=self.session) 
        # Note: Caller handles ValueError if not found, or we re-raise/let it bubble
        # Looking at controller, it catches ValueError. We can let it bubble.
        
        realm_id = CacheService.get_realm_id(realm_map)

        # Build context
        ctx = build_unified_context(principal, auth_context)

        # Resolve roles
        role_ids = []
        if role_names:
            target_role_ids = []
            for r_name in role_names:
                r_id = CacheService.resolve_role_id(realm_map, r_name)
                if r_id:
                    target_role_ids.append(r_id)
            
            if target_role_ids and not isinstance(principal, AnonymousPrincipal):
                principal_role_ids = getattr(principal, 'role_ids', None)
                if principal_role_ids is not None:
                    # In-memory filtering if available
                    role_ids = [rid for rid in target_role_ids if rid in principal_role_ids]
                else:
                    # DB filtering
                    q_verify = select(PrincipalRoles.role_id).where(
                        PrincipalRoles.principal_id == principal.id,
                        PrincipalRoles.role_id.in_(target_role_ids)
                    )
                    r_verify = await self.session.execute(q_verify)
                    role_ids = r_verify.scalars().all()
        else:
            if not isinstance(principal, AnonymousPrincipal):
                role_ids = getattr(principal, 'role_ids', []) or await CacheService.get_principal_roles(principal.id, db_session=self.session)
            
        role_ids_list = list(role_ids)

        # OPTIMIZATION: Batch resolve ALL external IDs upfront (single query)
        preresolved_ext_ids = await self._batch_resolve_external_ids(self.session, realm_id, req_access, realm_map)
        
        results = []
        audits = []

        # OPTIMIZATION: Process items in parallel with separate sessions
        if len(req_access) > 1:
            tasks = [
                self._process_item_parallel(
                    item, realm_id, realm_map,
                    principal.id, role_ids_list, ctx, preresolved_ext_ids
                )
                for item in req_access
            ]
            
            results_with_audits = await asyncio.gather(*tasks, return_exceptions=True)
            
            for r in results_with_audits:
                if isinstance(r, Exception):
                    logger.error(f"Parallel processing error: {r}")
                    raise r
                result, audit = r
                results.append(result)
                audits.append(audit)
        else:
            # Single item - use existing session
            for item in req_access:
                result, audit = await self._process_access_item_with_preresolved(
                    self.session, item, realm_id, realm_map, 
                    principal.id, role_ids_list, ctx, preresolved_ext_ids
                )
                results.append(result)
                audits.append(audit)
                
        return results, audits

    async def get_permitted_actions(
        self,
        realm_name: str,
        principal: Union[Principal, AnonymousPrincipal],
        resources: List[GetPermittedActionsItem],
        auth_context: Dict[str, Any] = None,
        role_names: List[str] = None
    ) -> Tuple[List[PermittedActionsResponseItem], List[AuditEntry]]:
        """
        Get the list of permitted actions for each resource.
        
        OPTIMIZED: Uses single batch query instead of O(resources × actions) queries.
        
        Returns a tuple of (results, audit_entries).
        """
        # Get Realm Map (cached)
        realm_map = await CacheService.get_realm_map(realm_name, db_session=self.session)
        realm_id = CacheService.get_realm_id(realm_map)
        
        # Resolve principal roles
        role_ids = []
        if role_names:
            for r_name in role_names:
                r_id = CacheService.resolve_role_id(realm_map, r_name)
                if r_id:
                    role_ids.append(r_id)
            if role_ids and not isinstance(principal, AnonymousPrincipal):
                principal_role_ids = getattr(principal, 'role_ids', None)
                if principal_role_ids is not None:
                    role_ids = [rid for rid in role_ids if rid in principal_role_ids]
        else:
            if not isinstance(principal, AnonymousPrincipal):
                role_ids = getattr(principal, 'role_ids', []) or await CacheService.get_principal_roles(principal.id, db_session=self.session)
        
        role_ids_list = list(role_ids)
        principal_id = principal.id if not isinstance(principal, AnonymousPrincipal) else 0
        
        # Build context
        ctx = build_unified_context(principal, auth_context)
        
        # Get action name to ID mapping from realm_map
        action_id_to_name = {}
        for key in realm_map:
            if key.startswith("action:"):
                action_name = key[7:]  # Remove "action:" prefix
                action_id = int(realm_map[key])
                action_id_to_name[action_id] = action_name
        
        # Process each resource type
        response_items: List[PermittedActionsResponseItem] = []
        audits: List[AuditEntry] = []
        
        for res_item in resources:
            # Resolve resource type ID
            try:
                # Get type ID from realm_map
                type_id = int(realm_map.get(f"type:{res_item.resource_type_name}"))
            except (KeyError, TypeError, ValueError):
                # Type not found - return empty actions
                if res_item.external_resource_ids:
                    for ext_id in res_item.external_resource_ids:
                        response_items.append(PermittedActionsResponseItem(
                            resource_type_name=res_item.resource_type_name,
                            external_resource_id=ext_id,
                            actions=[]
                        ))
                else:
                    response_items.append(PermittedActionsResponseItem(
                        resource_type_name=res_item.resource_type_name,
                        external_resource_id=None,
                        actions=[]
                    ))
                continue
            
            # Resolve external IDs to internal IDs
            internal_ids = None
            external_to_internal = {}
            internal_to_external = {}
            
            if res_item.external_resource_ids:
                # Batch lookup external -> internal IDs
                ext_ids_str = [str(e) for e in res_item.external_resource_ids]
                q_ext = text("""
                    SELECT external_id, resource_id
                    FROM external_ids
                    WHERE realm_id = :rid AND resource_type_id = :tid
                    AND external_id = ANY(:exts)
                """)
                r_ext = await self.session.execute(q_ext, {
                    "rid": realm_id,
                    "tid": type_id,
                    "exts": ext_ids_str
                })
                for row in r_ext:
                    external_to_internal[row.external_id] = row.resource_id
                    internal_to_external[row.resource_id] = row.external_id
                
                internal_ids = list(external_to_internal.values()) if external_to_internal else []
            
            # First: Query type-level ACLs directly (these apply to ALL requested resources, even non-existent)
            # This is critical for non-existent resources where the batch function won't return results
            q_type_level = text("""
                SELECT DISTINCT a.name as action_name
                FROM acl
                JOIN action a ON a.id = acl.action_id
                WHERE acl.realm_id = :rid
                  AND acl.resource_type_id = :tid
                  AND acl.resource_id IS NULL  -- Type-level ACL
                  AND (acl.compiled_sql IS NULL OR trim(acl.compiled_sql) = '' OR upper(trim(acl.compiled_sql)) = 'TRUE')
                  AND (
                      acl.principal_id = :pid
                      OR acl.role_id = ANY(:rids)
                      OR (acl.principal_id = 0 AND acl.role_id = 0)
                  )
            """)
            
            r_type_level = await self.session.execute(q_type_level, {
                "rid": realm_id,
                "tid": type_id,
                "pid": principal_id,
                "rids": role_ids_list
            })
            
            type_level_actions: set = set()
            for row in r_type_level:
                type_level_actions.add(row.action_name)
            
            # Second: If we have actual resources, call batch function for resource-level permissions
            resource_actions: Dict[Optional[int], set] = {}
            
            if internal_ids:
                query = text("""
                    SELECT resource_id, action_id, is_type_level
                    FROM get_permitted_actions_batch(:rid, :pid, :rids, :tid, :res_ids, :ctx)
                """)
                
                result = await self.session.execute(query, {
                    "rid": realm_id,
                    "pid": principal_id,
                    "rids": role_ids_list,
                    "tid": type_id,
                    "res_ids": internal_ids,
                    "ctx": json.dumps(ctx)
                })
                
                for row in result:
                    action_name = action_id_to_name.get(row.action_id)
                    if not action_name:
                        continue
                        
                    if row.is_type_level:
                        type_level_actions.add(action_name)
                    else:
                        if row.resource_id not in resource_actions:
                            resource_actions[row.resource_id] = set()
                        resource_actions[row.resource_id].add(action_name)

            
            # Build response items
            if res_item.external_resource_ids:
                for ext_id in res_item.external_resource_ids:
                    ext_id_str = str(ext_id)
                    internal_id = external_to_internal.get(ext_id_str)
                    
                    # Combine resource-level + type-level permissions
                    actions = set(type_level_actions)
                    if internal_id and internal_id in resource_actions:
                        actions |= resource_actions[internal_id]
                    
                    response_items.append(PermittedActionsResponseItem(
                        resource_type_name=res_item.resource_type_name,
                        external_resource_id=ext_id_str,
                        actions=list(actions)
                    ))
                    
                    audits.append(AuditEntry(
                        realm_id=realm_id,
                        principal_id=principal_id,
                        action_name="get_permitted_actions",
                        resource_type_name=res_item.resource_type_name,
                        decision=len(actions) > 0,
                        external_resource_ids=[ext_id_str]
                    ))
            else:
                # Type-level query only
                response_items.append(PermittedActionsResponseItem(
                    resource_type_name=res_item.resource_type_name,
                    external_resource_id=None,
                    actions=list(type_level_actions)
                ))
                
                audits.append(AuditEntry(
                    realm_id=realm_id,
                    principal_id=principal_id,
                    action_name="get_permitted_actions",
                    resource_type_name=res_item.resource_type_name,
                    decision=len(type_level_actions) > 0
                ))
        
        return response_items, audits

    async def _batch_resolve_external_ids(
        self,
        db: AsyncSession,
        realm_id: int,
        items: list,
        realm_map: dict
    ) -> Dict[str, Dict[str, int]]:
        """
        Batch resolve all external IDs across all items in a single query.
        Returns: {type_name: {external_id: resource_id}}
        """
        all_lookups: Dict[int, List[str]] = {}
        type_name_to_id: Dict[str, int] = {}
        
        for item in items:
            if item.external_resource_ids:
                try:
                    _, type_id = CacheService.resolve_ids(realm_map, item.action_name, item.resource_type_name)
                    type_name_to_id[item.resource_type_name] = type_id
                    
                    if type_id not in all_lookups:
                        all_lookups[type_id] = []
                    
                    for ext_id in item.external_resource_ids:
                        ext_str = str(ext_id)
                        if ext_str not in all_lookups[type_id]:
                            all_lookups[type_id].append(ext_str)
                except ValueError:
                    pass
        
        if not all_lookups:
            return {}
        
        result: Dict[str, Dict[str, int]] = {}
        cache_misses_by_type: Dict[int, List[str]] = {}
        
        for type_id, ext_ids in all_lookups.items():
            cached = await CacheService.get_external_id_mappings_batch(realm_id, type_id, ext_ids)
            
            type_name = next((name for name, tid in type_name_to_id.items() if tid == type_id), None)
            if type_name:
                result[type_name] = cached.copy()
            
            misses = [eid for eid in ext_ids if eid not in cached]
            if misses:
                cache_misses_by_type[type_id] = misses
        
        if cache_misses_by_type:
            for type_id, cache_misses in cache_misses_by_type.items():
                q_ext = text("""
                    SELECT resource_id, external_id, resource_type_id
                    FROM external_ids 
                    WHERE realm_id = :rid AND resource_type_id = :tid 
                    AND external_id IN :exts
                """)
                q_ext = q_ext.bindparams(bindparam("exts", expanding=True))
                r_ext = await db.execute(q_ext, {
                    "rid": realm_id,
                    "tid": type_id,
                    "exts": cache_misses
                })
                
                db_mappings = {}
                type_name = next((name for name, tid in type_name_to_id.items() if tid == type_id), None)
                
                for row in r_ext:
                    db_mappings[row.external_id] = row.resource_id
                    if type_name:
                        if type_name not in result:
                            result[type_name] = {}
                        result[type_name][row.external_id] = row.resource_id
                
                if db_mappings:
                    await CacheService.set_external_id_mappings_batch(realm_id, type_id, db_mappings)
        
        return result

    async def _process_item_parallel(
        self,
        item,
        realm_id: int,
        realm_map: dict,
        principal_id: int,
        role_ids_list: List[int],
        ctx: dict,
        preresolved_ext_ids: Dict[str, Dict[str, int]]
    ) -> Tuple[AccessResponseItem, AuditEntry]:
        """Process item with its own DB session for true parallelism."""
        async with AsyncSessionLocal() as db:
            return await self._process_access_item_with_preresolved(
                db, item, realm_id, realm_map,
                principal_id, role_ids_list, ctx, preresolved_ext_ids
            )

    async def _process_access_item_with_preresolved(
        self,
        db: AsyncSession,
        item,
        realm_id: int,
        realm_map: dict,
        principal_id: int,
        role_ids_list: List[int],
        ctx: dict,
        preresolved_ext_ids: Dict[str, Dict[str, int]]
    ) -> Tuple[AccessResponseItem, AuditEntry]:
        try:
            action_id, type_id = CacheService.resolve_ids(realm_map, item.action_name, item.resource_type_name)
        except ValueError as e:
            # We raise so upper layer catches
            raise ValueError(str(e))
        
        is_public = realm_map.get(f"type_public:{item.resource_type_name}") == "true"
        
        # Check cache
        if item.return_type == 'decision' and not item.external_resource_ids:
            cached_decision = await CacheService.get_type_level_decision(
                realm_id, principal_id, type_id, action_id, role_ids_list
            )
            if cached_decision is not None:
                result = AccessResponseItem(
                    action_name=item.action_name,
                    resource_type_name=item.resource_type_name,
                    answer=cached_decision
                )
                audit = AuditEntry(
                    realm_id=realm_id,
                    principal_id=principal_id,
                    action_name=item.action_name,
                    resource_type_name=item.resource_type_name,
                    decision=cached_decision
                )
                return result, audit
        
        internal_ids_filter = []
        external_map = {}
        
        if item.external_resource_ids:
            type_mappings = preresolved_ext_ids.get(item.resource_type_name, {})
            
            for ext_id in item.external_resource_ids:
                ext_str = str(ext_id)
                if ext_str in type_mappings:
                    res_id = type_mappings[ext_str]
                    internal_ids_filter.append(res_id)
                    external_map[res_id] = ext_str
            
            if not internal_ids_filter:
                # Resource external_id not found - but check for type-level ACL first!
                # Type-level ACLs (resource_id IS NULL) apply to ALL resources, even non-existent ones
                q_type_acl = text("""
                    SELECT compiled_sql 
                    FROM acl 
                    WHERE realm_id = :rid 
                      AND resource_type_id = :tid 
                      AND action_id = :aid 
                      AND resource_id IS NULL
                      AND (
                          principal_id = :pid 
                          OR role_id = ANY(:rids) 
                          OR (principal_id = 0 AND role_id = 0)
                      )
                """)
                r_type_acl = await db.execute(q_type_acl, {
                    "rid": realm_id,
                    "tid": type_id,
                    "aid": action_id,
                    "pid": principal_id,
                    "rids": role_ids_list
                })
                
                type_level_granted = False
                for sql_condition in r_type_acl.scalars().all():
                    if not sql_condition or not sql_condition.strip():
                        # Unconditional type-level access
                        type_level_granted = True
                        break
                    else:
                        # Evaluate condition
                        try:
                            eval_sql = sql_condition.replace('p_ctx', ':ctx')
                            q_eval = text(f"SELECT 1 WHERE {eval_sql}")
                            r_eval = await db.execute(q_eval, {"ctx": json.dumps(ctx)})
                            if r_eval.scalar():
                                type_level_granted = True
                                break
                        except Exception as e:
                            logger.warning(f"Failed to evaluate Type-Level ACL SQL: {sql_condition} Error: {e}")
                            continue
                
                if type_level_granted:
                    # Type-level ACL grants access - return all requested external IDs
                    final_answer = [str(ext_id) for ext_id in item.external_resource_ids]
                    answer = len(final_answer) > 0 if item.return_type == 'decision' else final_answer
                else:
                    answer = [] if item.return_type == 'id_list' else False
                    final_answer = []
                
                result = AccessResponseItem(
                    action_name=item.action_name,
                    resource_type_name=item.resource_type_name,
                    answer=answer
                )
                audit = AuditEntry(
                    realm_id=realm_id,
                    principal_id=principal_id,
                    action_name=item.action_name,
                    resource_type_name=item.resource_type_name,
                    decision=type_level_granted,
                    external_resource_ids=[str(ext_id) for ext_id in item.external_resource_ids] if type_level_granted else None
                )
                return result, audit
        
        if is_public and item.external_resource_ids:
            final_answer = list(external_map.values())
            answer = len(final_answer) > 0 if item.return_type == 'decision' else final_answer
            
            result = AccessResponseItem(
                action_name=item.action_name,
                resource_type_name=item.resource_type_name,
                answer=answer
            )
            audit = AuditEntry(
                realm_id=realm_id,
                principal_id=principal_id,
                action_name=item.action_name,
                resource_type_name=item.resource_type_name,
                decision=bool(answer) if isinstance(answer, bool) else len(answer) > 0,
                external_resource_ids=final_answer if final_answer else None
            )
            return result, audit
        
        # SQL execution
        resource_filter = internal_ids_filter if internal_ids_filter else None
        
        query = text("SELECT id FROM get_authorized_resources(:rid, :pid, :rids, :tid, :aid, :ctx, :res_ids)")
        
        result_proxy = await db.execute(query, {
            "rid": realm_id,
            "pid": principal_id,
            "rids": role_ids_list, 
            "aid": action_id,
            "tid": type_id,
            "ctx": json.dumps(ctx),
            "res_ids": resource_filter
        })
        
        authorized_internal_ids = set(result_proxy.scalars().all())
        
        final_answer = []
        final_external_ids = []
        
        if item.external_resource_ids:
            valid_ids = [mid for mid in internal_ids_filter if mid in authorized_internal_ids]
            final_answer = [external_map[mid] for mid in valid_ids]
            final_external_ids = final_answer
        else:
            if authorized_internal_ids:
                CHUNK_SIZE = 30000
                ids_list = list(authorized_internal_ids)
                all_external_ids = []
                
                for i in range(0, len(ids_list), CHUNK_SIZE):
                    chunk = ids_list[i:i + CHUNK_SIZE]
                    q_rev = text("""
                        SELECT external_id 
                        FROM external_ids 
                        WHERE realm_id = :rid AND resource_type_id = :tid 
                        AND resource_id IN :ids
                    """)
                    q_rev = q_rev.bindparams(bindparam("ids", expanding=True))
                    r_rev = await db.execute(q_rev, {
                        "rid": realm_id, 
                        "tid": type_id, 
                        "ids": chunk
                    })
                    all_external_ids.extend(r_rev.scalars().all())
                
                final_answer = all_external_ids
                final_external_ids = final_answer
        
        answer = len(final_answer) > 0 if item.return_type == 'decision' else final_answer
        
        # FALLBACK: If decision is False (no resources found) but we are asking for a general decision (e.g. Create),
        # we must check if there is a Type-Level ACL (resource_id IS NULL) that grants access.
        # The stored procedure 'get_authorized_resources' relies on joining with the 'resource' table,
        # so it fails to return True if the resource table is empty or has no matches, even if the user has "Create" permission.
        if item.return_type == 'decision' and not item.external_resource_ids and not answer:
            q_acl = text("""
                SELECT compiled_sql 
                FROM acl 
                WHERE realm_id = :rid 
                  AND resource_type_id = :tid 
                  AND action_id = :aid 
                  AND resource_id IS NULL
                  AND (
                      principal_id = :pid 
                      OR role_id = ANY(:rids) 
                      OR (principal_id = 0 AND role_id = 0)
                  )
            """)
            r_acl = await db.execute(q_acl, {
                "rid": realm_id,
                "tid": type_id,
                "aid": action_id,
                "pid": principal_id,
                "rids": role_ids_list
            })
            
            acl_rows = r_acl.scalars().all()
            
            for sql_condition in acl_rows:
                if not sql_condition or not sql_condition.strip():
                    # Unconditional access found
                    answer = True
                    break
                else:
                    # Context-based access: Evaluate the SQL condition
                    # We wrap it in a SELECT 1 WHERE ...
                    # Replace 'p_ctx' with bound parameter placeholder
                    # Note: compiled_sql expects 'p_ctx' -> need to bind it
                    
                    # Safety check: ensure strict SQL handling if needed. 
                    # Assuming compiled_sql is trusted from internal logic.
                    
                    # The stored procedure uses: replace(rec.compiled_sql, 'p_ctx', '$1')
                    # We can do similar but using SQLAlchemy bindparam
                    
                    # Attempt to evaluate
                    try:
                        # Replace p_ctx with :ctx for SQLAlchemy
                        eval_sql = sql_condition.replace('p_ctx', ':ctx')
                        
                        # We use 'SELECT 1 WHERE ...'
                        q_eval = text(f"SELECT 1 WHERE {eval_sql}")
                        r_eval = await db.execute(q_eval, {"ctx": json.dumps(ctx)})
                        if r_eval.scalar():
                            answer = True
                            break
                    except Exception as e:
                        logger.warning(f"Failed to evaluate Type-Level ACL SQL: {sql_condition} Error: {e}")
                        continue
        
        if item.return_type == 'decision' and not item.external_resource_ids:
            await CacheService.set_type_level_decision(
                realm_id, principal_id, type_id, action_id, role_ids_list,
                decision=bool(answer)
            )
        
        result = AccessResponseItem(
            action_name=item.action_name,
            resource_type_name=item.resource_type_name,
            answer=answer
        )
        
        audit = AuditEntry(
            realm_id=realm_id,
            principal_id=principal_id,
            action_name=item.action_name,
            resource_type_name=item.resource_type_name,
            decision=bool(answer) if isinstance(answer, bool) else len(answer) > 0,
            resource_ids=list(authorized_internal_ids) if authorized_internal_ids and not item.external_resource_ids else None,
            external_resource_ids=final_external_ids if final_external_ids else None
        )
        
        return result, audit

    async def get_authorization_conditions(
        self,
        realm_name: str,
        principal: Union[Principal, AnonymousPrincipal],
        resource_type_name: str,
        action_name: str,
        role_names: List[str] = None
    ) -> Dict[str, Any]:
        """
        Get authorization conditions as JSON DSL for SearchQuery conversion.
        
        This enables single-query authorization: the returned conditions can be
        converted to a SearchQuery and merged with user queries using
        SearchQuery.merge() for optimal database performance.
        
        Args:
            realm_name: Name of the realm
            principal: The principal (user) making the request
            resource_type_name: Name of the resource type
            action_name: Action being performed (e.g., "read", "update")
            role_names: Optional role names to filter by
            
        Returns:
            Dict with:
                - filter_type: 'granted_all', 'denied_all', or 'conditions'
                - conditions_dsl: JSON condition DSL (or None)
                - external_ids: List of granted resource external IDs (or None)
                - has_context_refs: Whether conditions reference $context.* or $principal.*
        """
        # Get Realm Map (cached)
        realm_map = await CacheService.get_realm_map(realm_name, db_session=self.session)
        realm_id = CacheService.get_realm_id(realm_map)
        
        # Resolve resource type and action IDs
        try:
            type_id = int(realm_map[f"type:{resource_type_name}"])
            action_id = int(realm_map[f"action:{action_name}"])
        except (KeyError, TypeError, ValueError) as e:
            raise ValueError(f"Unknown resource type or action: {resource_type_name}/{action_name}")
        
        # Resolve roles
        role_ids = []
        if role_names:
            for r_name in role_names:
                role_id = realm_map.get(f"role:{r_name}")
                if role_id:
                    role_ids.append(int(role_id))
            # Filter to roles the principal actually has
            if role_ids and not isinstance(principal, AnonymousPrincipal):
                stmt = select(PrincipalRoles.role_id).where(
                    PrincipalRoles.principal_id == principal.id,
                    PrincipalRoles.role_id.in_(role_ids)
                )
                result = await self.session.execute(stmt)
                role_ids = list(result.scalars().all())
        else:
            # Get all roles for the principal
            if not isinstance(principal, AnonymousPrincipal):
                stmt = select(PrincipalRoles.role_id).where(
                    PrincipalRoles.principal_id == principal.id
                )
                result = await self.session.execute(stmt)
                role_ids = list(result.scalars().all())
        
        principal_id = principal.id if not isinstance(principal, AnonymousPrincipal) else 0
        
        # Call the PostgreSQL function
        query = text("""
            SELECT filter_type, conditions_dsl, external_ids, has_context_refs
            FROM get_authorization_conditions(:realm_id, :principal_id, :role_ids, :type_id, :action_id)
        """)
        
        result = await self.session.execute(query, {
            "realm_id": realm_id,
            "principal_id": principal_id,
            "role_ids": role_ids,
            "type_id": type_id,
            "action_id": action_id
        })
        
        row = result.fetchone()
        
        if row is None:
            # No result from function - treat as denied
            return {
                "filter_type": "denied_all",
                "conditions_dsl": None,
                "external_ids": None,
                "has_context_refs": False
            }
        
        return {
            "filter_type": row.filter_type,
            "conditions_dsl": row.conditions_dsl,
            "external_ids": list(row.external_ids) if row.external_ids else None,
            "has_context_refs": row.has_context_refs
        }
