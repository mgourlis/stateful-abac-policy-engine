"""
Manifest Service - Handles declarative realm configuration processing

This service provides optimized batch processing for realm manifests with
comprehensive logging and progress tracking.
"""
import logging
import time
import json
from typing import Dict, Any, Literal, Optional, Set
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, text, insert
from sqlalchemy.orm import selectinload
from common.models import (
    Realm, RealmKeycloakConfig, ResourceType, Action, AuthRole, 
    Principal, Resource, ACL, ExternalID, PrincipalRoles
)

logger = logging.getLogger(__name__)


def _truncate(value: str, max_len: int = 200) -> str:
    """Truncate a string to max_len, appending '...' if truncated."""
    if len(value) <= max_len:
        return value
    return value[:max_len] + "..."


class ManifestService:
    """Service for processing realm manifests with optimized batch operations."""
    
    @staticmethod
    async def _build_lookup_maps(
        db: AsyncSession, 
        realm_id: int
    ) -> Dict[str, Dict[str, Any]]:
        """
        Pre-fetch all lookup data for the realm to avoid N+1 queries.
        """
        start = time.monotonic()
        
        # Fetch all resource types
        stmt = select(ResourceType).where(ResourceType.realm_id == realm_id)
        result = await db.execute(stmt)
        resource_types = result.scalars().all()
        rt_by_name = {rt.name: rt for rt in resource_types}
        rt_by_id = {rt.id: rt for rt in resource_types}
        
        # Fetch all actions
        stmt = select(Action).where(Action.realm_id == realm_id)
        result = await db.execute(stmt)
        actions = result.scalars().all()
        action_by_name = {a.name: a for a in actions}
        action_by_id = {a.id: a for a in actions}
        
        # Fetch all roles
        stmt = select(AuthRole).where(AuthRole.realm_id == realm_id)
        result = await db.execute(stmt)
        roles = result.scalars().all()
        role_by_name = {r.name: r for r in roles}
        role_by_id = {r.id: r for r in roles}
        
        # Fetch all principals
        stmt = select(Principal).options(selectinload(Principal.roles)).where(Principal.realm_id == realm_id)
        result = await db.execute(stmt)
        principals = result.scalars().all()
        principal_by_username = {p.username: p for p in principals}
        principal_by_id = {p.id: p for p in principals}
        
        elapsed = (time.monotonic() - start) * 1000
        logger.debug(
            f"Built lookup maps in {elapsed:.1f}ms: "
            f"{len(rt_by_name)} resource_types, {len(action_by_name)} actions, "
            f"{len(role_by_name)} roles, {len(principal_by_username)} principals"
        )
        
        return {
            "resource_types": {"by_name": rt_by_name, "by_id": rt_by_id},
            "actions": {"by_name": action_by_name, "by_id": action_by_id},
            "roles": {"by_name": role_by_name, "by_id": role_by_id},
            "principals": {"by_username": principal_by_username, "by_id": principal_by_id},
        }
    
    @staticmethod
    async def _build_external_id_map(
        db: AsyncSession,
        realm_id: int,
        resource_type_id: Optional[int] = None
    ) -> Dict[str, int]:
        """
        Build a map of external_id -> resource_id for fast lookups.
        """
        stmt = select(ExternalID.external_id, ExternalID.resource_id).where(
            ExternalID.realm_id == realm_id
        )
        if resource_type_id:
            stmt = stmt.where(ExternalID.resource_type_id == resource_type_id)
        
        result = await db.execute(stmt)
        return {row[0]: row[1] for row in result.fetchall()}
    
    @staticmethod
    async def apply_manifest(
        db: AsyncSession,
        manifest_input: str | Dict[str, Any],
        mode: Literal['replace', 'create', 'update'] = 'update'
    ) -> Dict[str, Any]:
        """
        Apply a manifest to configure a realm.
        """
        total_start = time.monotonic()
        
        # Load manifest if path provided
        if isinstance(manifest_input, str):
            logger.info(f"Loading manifest from file: {manifest_input}")
            file_start = time.monotonic()
            with open(manifest_input, 'r') as f:
                manifest_data = json.load(f)
            logger.info(f"Manifest file loaded in {(time.monotonic() - file_start) * 1000:.1f}ms")
        else:
            manifest_data = manifest_input

        results = {}
        
        # Log manifest summary
        logger.info(
            f"Processing manifest: mode={mode}, "
            f"resource_types={len(manifest_data.get('resource_types', []))}, "
            f"actions={len(manifest_data.get('actions', []))}, "
            f"roles={len(manifest_data.get('roles', []))}, "
            f"principals={len(manifest_data.get('principals', []))}, "
            f"resources={len(manifest_data.get('resources', []))}, "
            f"acls={len(manifest_data.get('acls', []))}"
        )
        
        # 1. Process Realm
        section_start = time.monotonic()
        realm_data = manifest_data.get("realm")
        if not realm_data:
            raise ValueError("Manifest must contain 'realm' definition")
        
        realm_name = realm_data["name"]
        logger.info(f"Processing realm: {realm_name}")
        
        # Handle Replace Mode: Delete realm if exists
        if mode == 'replace':
            stmt = select(Realm).where(Realm.name == realm_name)
            result = await db.execute(stmt)
            existing_realm = result.scalar_one_or_none()
            
            if existing_realm:
                from common.application.realm_service import RealmService
                realm_service = RealmService(db)
                await realm_service.delete_realm(existing_realm.id)
                # await db.commit() # delete_realm already commits
                logger.info(f"Deleted existing realm '{realm_name}' for replace mode")
                results["realm_deleted"] = True
        
        # Check if realm exists
        stmt = select(Realm).options(selectinload(Realm.keycloak_config)).where(Realm.name == realm_name)
        result = await db.execute(stmt)
        realm = result.scalar_one_or_none()
        
        if realm:
            if mode == 'create':
                logger.warning(f"Realm '{realm_name}' already exists, skipping creation (create mode)")
                results["realm"] = "skipped"
            else:  # update mode
                # Update realm
                if "description" in realm_data:
                    realm.description = realm_data["description"]
                
                # Handle Keycloak config
                if "keycloak_config" in realm_data:
                    kc_data = realm_data["keycloak_config"]
                    if realm.keycloak_config:
                        # Update existing config
                        for key, value in kc_data.items():
                            setattr(realm.keycloak_config, key, value)
                    else:
                        # Create new config
                        kc_config = RealmKeycloakConfig(realm_id=realm.id, **kc_data)
                        db.add(kc_config)
                
                await db.commit()
                await db.refresh(realm)
                results["realm"] = "updated"
                logger.debug(f"Realm '{realm_name}' updated")
        else:
            # Create new realm
            realm = Realm(name=realm_name, description=realm_data.get("description"))
            db.add(realm)
            await db.flush()
            
            # Create partitions for the new realm
            rid = realm.id
            logger.debug(f"Creating partitions for realm {rid}")
            await db.execute(text(f"CREATE TABLE IF NOT EXISTS resource_{rid} PARTITION OF resource FOR VALUES IN ({rid}) PARTITION BY LIST (resource_type_id)"))
            await db.execute(text(f"CREATE TABLE IF NOT EXISTS acl_{rid} PARTITION OF acl FOR VALUES IN ({rid}) PARTITION BY LIST (resource_type_id)"))
            await db.execute(text(f"CREATE TABLE IF NOT EXISTS external_ids_{rid} PARTITION OF external_ids FOR VALUES IN ({rid}) PARTITION BY LIST (resource_type_id)"))
            
            # Add Keycloak config if provided
            if "keycloak_config" in realm_data:
                kc_config = RealmKeycloakConfig(realm_id=realm.id, **realm_data["keycloak_config"])
                db.add(kc_config)
            
            await db.commit()
            await db.refresh(realm)
            results["realm"] = "created"
            logger.info(f"Realm '{realm_name}' created with id={realm.id}")
        
        realm_id = realm.id
        logger.debug(f"Realm processing completed in {(time.monotonic() - section_start) * 1000:.1f}ms")
        
        # 2. Resource Types
        rt_data = manifest_data.get("resource_types", [])
        if rt_data:
            section_start = time.monotonic()
            logger.info(f"Processing {len(rt_data)} resource types...")
            
            # Pre-fetch existing resource types
            stmt = select(ResourceType).where(ResourceType.realm_id == realm_id)
            result = await db.execute(stmt)
            existing_rts = {rt.name: rt for rt in result.scalars().all()}
            
            created, updated = 0, 0
            for item in rt_data:
                rt_name = item["name"]
                rt = existing_rts.get(rt_name)
                
                if rt:
                    rt.is_public = item.get("is_public", False)
                    updated += 1
                else:
                    rt = ResourceType(realm_id=realm_id, **item)
                    db.add(rt)
                    await db.flush()
                    
                    # Create sub-partitions for the new resource type
                    tid = rt.id
                    await db.execute(text(f"CREATE TABLE IF NOT EXISTS resource_{realm_id}_{tid} PARTITION OF resource_{realm_id} FOR VALUES IN ({tid})"))
                    await db.execute(text(f"CREATE TABLE IF NOT EXISTS acl_{realm_id}_{tid} PARTITION OF acl_{realm_id} FOR VALUES IN ({tid})"))
                    await db.execute(text(f"CREATE TABLE IF NOT EXISTS external_ids_{realm_id}_{tid} PARTITION OF external_ids_{realm_id} FOR VALUES IN ({tid})"))
                    
                    existing_rts[rt_name] = rt  # Update cache
                    created += 1
            
            await db.commit()
            results["resource_types"] = {"created": created, "updated": updated}
            logger.info(
                f"Resource types: created={created}, updated={updated} "
                f"({(time.monotonic() - section_start) * 1000:.1f}ms)"
            )
        
        # 3. Actions
        act_data = manifest_data.get("actions", [])
        if act_data:
            section_start = time.monotonic()
            logger.info(f"Processing {len(act_data)} actions...")
            
            # Pre-fetch existing actions
            stmt = select(Action).where(Action.realm_id == realm_id)
            result = await db.execute(stmt)
            existing_actions: Set[str] = {a.name for a in result.scalars().all()}
            
            created = 0
            new_actions = []
            for item in act_data:
                name = item if isinstance(item, str) else item["name"]
                if name not in existing_actions:
                    new_actions.append(Action(realm_id=realm_id, name=name))
                    existing_actions.add(name)  # Prevent duplicates in batch
                    created += 1
            
            if new_actions:
                db.add_all(new_actions)
                await db.commit()
            
            results["actions"] = {"created": created}
            logger.info(f"Actions: created={created} ({(time.monotonic() - section_start) * 1000:.1f}ms)")
        
        # 4. Roles
        role_data = manifest_data.get("roles", [])
        if role_data:
            section_start = time.monotonic()
            logger.info(f"Processing {len(role_data)} roles...")
            
            # Pre-fetch existing roles
            stmt = select(AuthRole).where(AuthRole.realm_id == realm_id)
            result = await db.execute(stmt)
            existing_roles = {r.name: r for r in result.scalars().all()}
            
            created, updated = 0, 0
            new_roles = []
            for item in role_data:
                role_name = item["name"]
                role = existing_roles.get(role_name)
                
                if role:
                    if "attributes" in item:
                        role.attributes = item["attributes"]
                    updated += 1
                else:
                    new_role = AuthRole(realm_id=realm_id, **item)
                    new_roles.append(new_role)
                    created += 1
            
            if new_roles:
                db.add_all(new_roles)
            await db.commit()
            
            results["roles"] = {"created": created, "updated": updated}
            logger.info(
                f"Roles: created={created}, updated={updated} "
                f"({(time.monotonic() - section_start) * 1000:.1f}ms)"
            )
        
        # Build lookup maps
        lookup_maps = await ManifestService._build_lookup_maps(db, realm_id)
        
        # 5. Principals
        principal_data = manifest_data.get("principals", [])
        if principal_data:
            section_start = time.monotonic()
            logger.info(f"Processing {len(principal_data)} principals...")
            
            # Pre-fetch existing principals
            existing_principals = lookup_maps["principals"]["by_username"]
            role_map = lookup_maps["roles"]["by_name"]
            
            created = 0
            for item in principal_data:
                username = item["username"]
                if username in existing_principals:
                    continue
                
                principal = Principal(
                    realm_id=realm_id,
                    username=username,
                    attributes=item.get("attributes")
                )
                db.add(principal)
                await db.flush()
                
                # Assign roles if provided - batch insert
                if "roles" in item:
                    role_assignments = []
                    for role_name in item["roles"]:
                        role = role_map.get(role_name)
                        if role:
                            role_assignments.append({
                                "principal_id": principal.id,
                                "role_id": role.id
                            })
                    
                    if role_assignments:
                        await db.execute(insert(PrincipalRoles), role_assignments)
                
                existing_principals[username] = principal  # Update cache
                created += 1
            
            await db.commit()
            results["principals"] = {"created": created}
            logger.info(f"Principals: created={created} ({(time.monotonic() - section_start) * 1000:.1f}ms)")
        
        # 5.5. Keycloak Sync
        if "keycloak_config" in realm_data:
            section_start = time.monotonic()
            kc_config = realm_data["keycloak_config"]
            
            if kc_config.get("client_secret"):
                logger.info("Syncing with Keycloak (roles and principals)...")
                try:
                    from common.services.sync_service import SyncService
                    sync_service = SyncService(db)
                    await sync_service.sync_realm(realm_id)
                    results["keycloak_sync"] = "completed"
                    logger.info(f"Keycloak sync completed in {(time.monotonic() - section_start) * 1000:.1f}ms")
                except Exception as e:
                    logger.error(f"Keycloak sync failed: {_truncate(str(e), 500)}")
                    results["keycloak_sync"] = {"error": str(e)}
            else:
                logger.debug("Keycloak sync skipped: no client_secret provided (read-only config)")
                results["keycloak_sync"] = "skipped"
        
        # Refresh lookup maps
        lookup_maps = await ManifestService._build_lookup_maps(db, realm_id)
        
        # 6. Resources
        res_data = manifest_data.get("resources", [])
        if res_data:
            section_start = time.monotonic()
            total_resources = len(res_data)
            logger.info(f"Processing {total_resources} resources (bulk mode)...")
            
            from common.services.geometry_service import GeometryService
            import json as json_module
            
            rt_map = lookup_maps["resource_types"]["by_name"]
            
            resources_by_type: Dict[str, list] = {}
            for item in res_data:
                type_name = item.get("type")
                if type_name not in resources_by_type:
                    resources_by_type[type_name] = []
                resources_by_type[type_name].append(item)
            
            created, updated, skipped = 0, 0, 0
            BATCH_SIZE = 100
            
            for type_name, type_resources in resources_by_type.items():
                rt = rt_map.get(type_name)
                if not rt:
                    logger.warning(f"Resource type '{type_name}' not found, skipping {len(type_resources)} resources")
                    skipped += len(type_resources)
                    continue
                
                type_start = time.monotonic()
                logger.info(f"  Processing {len(type_resources)} resources of type '{type_name}'...")
                
                ext_id_map = await ManifestService._build_external_id_map(db, realm_id, rt.id)
                
                new_resources = []
                update_resources = []
                
                for item in type_resources:
                    external_id = item.get("external_id")
                    if not external_id:
                        skipped += 1
                        continue
                    
                    if external_id in ext_id_map:
                        if "attributes" in item:
                            update_resources.append((ext_id_map[external_id], item["attributes"]))
                        updated += 1
                    else:
                        new_resources.append(item)
                
                # Bulk update
                if update_resources:
                    logger.debug(f"    Bulk updating {len(update_resources)} existing resources...")
                    for i in range(0, len(update_resources), BATCH_SIZE):
                        batch = update_resources[i:i + BATCH_SIZE]
                        case_clauses = []
                        resource_ids = []
                        for rid, attrs in batch:
                            resource_ids.append(rid)
                            attrs_json = json_module.dumps(attrs) if attrs else 'null'
                            attrs_json_escaped = attrs_json.replace("'", "''")
                            case_clauses.append(f"WHEN id = {rid} THEN '{attrs_json_escaped}'::jsonb")
                        
                        if case_clauses:
                            ids_str = ','.join(str(rid) for rid in resource_ids)
                            update_sql = text(f"""
                                UPDATE resource 
                                SET attributes = CASE {' '.join(case_clauses)} END
                                WHERE id IN ({ids_str})
                            """)
                            await db.execute(update_sql)
                        
                        if (i + BATCH_SIZE) % 50000 == 0:
                            await db.commit()
                            logger.debug(f"    Updated {min(i + BATCH_SIZE, len(update_resources))}/{len(update_resources)} resources")
                    
                    await db.commit()
                
                # Bulk insert
                if new_resources:
                    logger.info(f"    Bulk inserting {len(new_resources)} new resources...")
                    
                    for batch_idx in range(0, len(new_resources), BATCH_SIZE):
                        batch = new_resources[batch_idx:batch_idx + BATCH_SIZE]
                        batch_start = time.monotonic()
                        
                        resource_values = []
                        external_id_data = [] 
                        
                        for idx, item in enumerate(batch):
                            external_id = item.get("external_id")
                            geo = None
                            if "geometry" in item and item["geometry"]:
                                try:
                                    srid = item.get("srid")
                                    geo = GeometryService.parse_to_ewkt(item["geometry"], srid=srid)
                                except Exception as e:
                                    logger.error(f"Failed to parse geometry for resource {external_id}: {e}")
                                    pass
                            
                            attrs = item.get("attributes") or {}
                            attrs_json = json_module.dumps(attrs)
                            
                            resource_values.append({
                                "realm_id": realm_id,
                                "resource_type_id": rt.id,
                                "attributes": attrs_json,
                                "geometry": geo
                            })
                            external_id_data.append(external_id)
                        
                        if resource_values:
                            values_parts = []
                            for rv in resource_values:
                                if rv['attributes']:
                                    attrs_escaped = rv['attributes'].replace("'", "''")
                                    attrs_val = f"'{attrs_escaped}'::jsonb"
                                else:
                                    attrs_val = "NULL"
                                if rv['geometry']:
                                    geo_escaped = rv['geometry'].replace("'", "''")
                                    geo_val = f"ST_GeomFromEWKT('{geo_escaped}')"
                                else:
                                    geo_val = "NULL"
                                values_parts.append(
                                    f"({rv['realm_id']}, {rv['resource_type_id']}, {attrs_val}, {geo_val})"
                                )
                            
                            insert_sql = text(f"""
                                INSERT INTO resource (realm_id, resource_type_id, attributes, geometry)
                                VALUES {','.join(values_parts)}
                                RETURNING id
                            """)
                            result = await db.execute(insert_sql)
                            new_ids = [row[0] for row in result.fetchall()]
                            
                            ext_id_values = []
                            for new_id, ext_id in zip(new_ids, external_id_data):
                                ext_id_escaped = ext_id.replace("'", "''")
                                ext_id_values.append(
                                    f"({realm_id}, {rt.id}, '{ext_id_escaped}', {new_id})"
                                )
                            
                            ext_insert_sql = text(f"""
                                INSERT INTO external_ids (realm_id, resource_type_id, external_id, resource_id)
                                VALUES {','.join(ext_id_values)}
                            """)
                            await db.execute(ext_insert_sql)
                            
                            created += len(new_ids)
                        
                        await db.commit()
                        
                        batch_elapsed = (time.monotonic() - batch_start) * 1000
                        progress = batch_idx + len(batch)
                        batch_num = batch_idx // BATCH_SIZE + 1
                        total_batches = (len(new_resources) + BATCH_SIZE - 1) // BATCH_SIZE
                        if batch_num % 5 == 0 or progress >= len(new_resources):
                            logger.info(
                                f"    Batch {batch_num}/{total_batches}: inserted {progress}/{len(new_resources)} resources "
                                f"({batch_elapsed:.0f}ms/batch)"
                            )
                
                type_elapsed = (time.monotonic() - type_start) * 1000
                logger.info(f"  Type '{type_name}' completed in {type_elapsed:.0f}ms")
            
            results["resources"] = {"created": created, "updated": updated, "skipped": skipped}
            logger.info(
                f"Resources: created={created}, updated={updated}, skipped={skipped} "
                f"({(time.monotonic() - section_start) * 1000:.1f}ms)"
            )
        
        # 7. ACLs
        acl_data = manifest_data.get("acls", [])
        if acl_data:
            section_start = time.monotonic()
            total_acls = len(acl_data)
            logger.info(f"Processing {total_acls} ACLs...")
            
            lookup_maps = await ManifestService._build_lookup_maps(db, realm_id)
            rt_map = lookup_maps["resource_types"]["by_name"]
            action_map = lookup_maps["actions"]["by_name"]
            role_map = lookup_maps["roles"]["by_name"]
            principal_map = lookup_maps["principals"]["by_username"]
            
            ext_id_map = await ManifestService._build_external_id_map(db, realm_id)
            
            created, skipped = 0, 0
            skip_reasons: Dict[str, int] = {}
            progress_interval = max(1, total_acls // 5)
            
            for idx, item in enumerate(acl_data):
                type_name = item.get("resource_type")
                rt = rt_map.get(type_name)
                if not rt:
                    skip_reasons[f"resource_type:{type_name}"] = skip_reasons.get(f"resource_type:{type_name}", 0) + 1
                    skipped += 1
                    continue
                
                action_name = item.get("action")
                action = action_map.get(action_name)
                if not action:
                    skip_reasons[f"action:{action_name}"] = skip_reasons.get(f"action:{action_name}", 0) + 1
                    skipped += 1
                    continue
                
                role_id = None
                principal_id = None
                
                if "role" in item:
                    role = role_map.get(item["role"])
                    if role:
                        role_id = role.id
                
                if "principal" in item:
                    if item["principal"] == "anonymous":
                        principal_id = 0
                    else:
                        principal = principal_map.get(item["principal"])
                        if principal:
                            principal_id = principal.id
                elif "principal_id" in item:
                    principal_id = item["principal_id"]

                resource_id = None
                if "resource_external_id" in item:
                    resource_id = ext_id_map.get(item["resource_external_id"])
                
                conditions = item.get("conditions")
                if conditions is None or conditions == "null":
                    conditions = None
                    
                acl = ACL(
                    realm_id=realm_id,
                    resource_type_id=rt.id,
                    action_id=action.id,
                    role_id=role_id,
                    principal_id=principal_id,
                    resource_id=resource_id,
                    conditions=conditions
                )
                db.add(acl)
                created += 1
                
                if (idx + 1) % progress_interval == 0:
                    logger.info(f"  ACLs progress: {idx + 1}/{total_acls} ({(idx + 1) * 100 // total_acls}%)")
            
            try:
                await db.commit()
                results["acls"] = {"created": created, "skipped": skipped}
                elapsed = (time.monotonic() - section_start) * 1000
                logger.info(f"ACLs: created={created}, skipped={skipped} ({elapsed:.1f}ms)")
                
                if skip_reasons:
                    top_reasons = sorted(skip_reasons.items(), key=lambda x: -x[1])[:10]
                    reasons_str = ", ".join(f"{k}({v})" for k, v in top_reasons)
                    logger.warning(f"ACL skip reasons (top 10): {_truncate(reasons_str, 500)}")
                    
            except Exception as e:
                logger.error(f"ACL commit failed: {_truncate(str(e), 500)}")
                await db.rollback()
                results["acls"] = {"created": 0, "error": str(e)}
        
        total_elapsed = (time.monotonic() - total_start) * 1000
        logger.info(f"Manifest application completed in {total_elapsed:.1f}ms")
        results["elapsed_ms"] = round(total_elapsed, 1)
        
        return results
    
    @staticmethod
    async def export_manifest(db: AsyncSession, realm_name: str) -> Dict[str, Any]:
        """
        Export a realm's configuration as a manifest JSON.
        """
        start = time.monotonic()
        logger.info(f"Exporting manifest for realm: {realm_name}")
        
        stmt = select(Realm).options(selectinload(Realm.keycloak_config)).where(Realm.name == realm_name)
        result = await db.execute(stmt)
        realm = result.scalar_one_or_none()
        
        if not realm:
            raise ValueError(f"Realm '{realm_name}' not found")
        
        manifest: Dict[str, Any] = {
            "realm": {
                "name": realm.name,
                "description": realm.description
            }
        }
        
        if realm.keycloak_config:
            kc = realm.keycloak_config
            manifest["realm"]["keycloak_config"] = {
                "server_url": kc.server_url,
                "keycloak_realm": kc.keycloak_realm,
                "client_id": kc.client_id,
                "verify_ssl": kc.verify_ssl,
                "sync_cron": kc.sync_cron,
                "sync_groups": kc.sync_groups
            }
            if kc.settings:
                manifest["realm"]["keycloak_config"]["settings"] = kc.settings
        
        # 2. Resource Types
        stmt = select(ResourceType).where(ResourceType.realm_id == realm.id)
        result = await db.execute(stmt)
        resource_types = result.scalars().all()
        
        if resource_types:
            manifest["resource_types"] = [
                {"name": rt.name, "is_public": rt.is_public}
                for rt in resource_types
            ]
        
        # 3. Actions
        stmt = select(Action).where(Action.realm_id == realm.id)
        result = await db.execute(stmt)
        actions = result.scalars().all()
        
        if actions:
            manifest["actions"] = [action.name for action in actions]
        
        # 4. Roles
        stmt = select(AuthRole).where(AuthRole.realm_id == realm.id)
        result = await db.execute(stmt)
        roles = result.scalars().all()
        
        if roles:
            manifest["roles"] = []
            for role in roles:
                role_dict = {"name": role.name}
                if role.attributes:
                    role_dict["attributes"] = role.attributes
                manifest["roles"].append(role_dict)
        
        # 5. Principals
        stmt = select(Principal).options(selectinload(Principal.roles)).where(Principal.realm_id == realm.id)
        result = await db.execute(stmt)
        principals = result.scalars().all()
        
        if principals:
            manifest["principals"] = []
            for principal in principals:
                principal_dict = {"username": principal.username}
                if principal.attributes:
                    principal_dict["attributes"] = principal.attributes
                if principal.roles:
                    principal_dict["roles"] = [role.name for role in principal.roles]
                manifest["principals"].append(principal_dict)
        
        # 6. Resources
        stmt = select(Resource).options(selectinload(Resource.external_ids)).where(Resource.realm_id == realm.id)
        result = await db.execute(stmt)
        resources = result.scalars().all()
        
        if resources:
            type_map = {rt.id: rt.name for rt in resource_types}
            manifest["resources"] = []
            for resource in resources:
                resource_dict = {
                    "type": type_map.get(resource.resource_type_id, "unknown")
                }
                if resource.external_ids:
                    resource_dict["external_id"] = resource.external_ids[0].external_id
                if resource.attributes:
                    resource_dict["attributes"] = resource.attributes
                if resource.geometry:
                    from geoalchemy2.shape import to_shape
                    import shapely.geometry
                    try:
                        sh = to_shape(resource.geometry)
                        resource_dict["geometry"] = shapely.geometry.mapping(sh)
                    except Exception:
                        pass
                manifest["resources"].append(resource_dict)
        
        # 7. ACLs
        stmt = select(ACL).where(ACL.realm_id == realm.id)
        result = await db.execute(stmt)
        acls = result.scalars().all()
        
        if acls:
            type_map = {rt.id: rt.name for rt in resource_types}
            action_map = {a.id: a.name for a in actions}
            role_map = {r.id: r.name for r in roles}
            principal_map = {p.id: p.username for p in principals}
            
            resource_ext_id_map = {}
            for res in resources:
                if res.external_ids:
                    resource_ext_id_map[res.id] = res.external_ids[0].external_id
            
            manifest["acls"] = []
            for acl in acls:
                acl_dict = {
                    "resource_type": type_map.get(acl.resource_type_id, "unknown"),
                    "action": action_map.get(acl.action_id, "unknown")
                }
                if acl.role_id:
                    acl_dict["role"] = role_map.get(acl.role_id, "unknown")
                elif acl.principal_id is not None:
                    if acl.principal_id == 0:
                        acl_dict["principal"] = "anonymous"
                    else:
                        acl_dict["principal"] = principal_map.get(acl.principal_id, "unknown")
                
                if acl.resource_id and acl.resource_id in resource_ext_id_map:
                    acl_dict["resource_external_id"] = resource_ext_id_map[acl.resource_id]
                
                if acl.conditions:
                    acl_dict["conditions"] = acl.conditions
                
                manifest["acls"].append(acl_dict)
        
        elapsed = (time.monotonic() - start) * 1000
        logger.info(f"Manifest export completed in {elapsed:.1f}ms")
        
        return manifest
