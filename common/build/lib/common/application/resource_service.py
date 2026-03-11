from typing import Optional, List, Union
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from sqlalchemy.orm import selectinload
from geoalchemy2.shape import to_shape
import shapely.geometry

from common.models import Resource, ExternalID, ResourceType
from common.schemas.realm_api import ResourceCreate, ResourceUpdate, BatchResourceOperation, ResourceRead
from common.services.geometry_service import GeometryService

class ResourceService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_resource(self, realm_id: int, resource_in: ResourceCreate) -> ResourceRead:
        # Check Upsert via External ID
        if resource_in.external_id:
            ext_stmt = select(ExternalID).where(
                ExternalID.realm_id == realm_id,
                ExternalID.resource_type_id == resource_in.resource_type_id,
                ExternalID.external_id == resource_in.external_id
            )
            ext_res = await self.session.execute(ext_stmt)
            ext_obj_ref = ext_res.scalar_one_or_none()
            
            if ext_obj_ref:
                return await self.update_resource_internal(realm_id, ext_obj_ref.resource_id, ResourceUpdate(
                    resource_type_id=resource_in.resource_type_id,
                    attributes=resource_in.attributes,
                    geometry=resource_in.geometry,
                    srid=resource_in.srid
                ))

        res_data = resource_in.model_dump(exclude={"external_id", "geometry", "srid"})
        res_data["attributes"] = res_data.get("attributes", {}) or {}
        
        geo = None
        if resource_in.geometry is not None:
             geo = GeometryService.parse(resource_in.geometry, srid=resource_in.srid)

        resource = Resource(**res_data, realm_id=realm_id, geometry=geo)
        self.session.add(resource)
        await self.session.flush()
        
        if resource_in.external_id:
            ext_obj = ExternalID(
                resource_id=resource.id,
                realm_id=realm_id,
                resource_type_id=resource_in.resource_type_id,
                external_id=resource_in.external_id
            )
            self.session.add(ext_obj)
        
        await self.session.commit()
        await self.session.refresh(resource)

        stmt = select(Resource).options(selectinload(Resource.external_ids)).where(Resource.id == resource.id, Resource.realm_id == realm_id)
        result = await self.session.execute(stmt)
        resource = result.scalar_one_or_none()
        
        # Pass external_id directly - we just created it above
        return self._to_read(resource, resource_in.external_id)

    async def get_resource(self, realm_id: int, resource_id: int) -> Optional[ResourceRead]:
        stmt = select(Resource).options(selectinload(Resource.external_ids)).where(Resource.id == resource_id, Resource.realm_id == realm_id)
        result = await self.session.execute(stmt)
        resource = result.scalar_one_or_none()
        if not resource:
            return None
        return self._to_read(resource)

    async def get_resource_by_external_id(self, realm_id: int, type_id_or_name: str, external_id: str) -> Optional[ResourceRead]:
        type_id = await self._resolve_type_id(realm_id, type_id_or_name)
        if type_id is None:
            return None

        stmt = select(ExternalID.resource_id).where(
            ExternalID.realm_id == realm_id,
            ExternalID.resource_type_id == type_id,
            ExternalID.external_id == external_id
        )
        result = await self.session.execute(stmt)
        rid = result.scalar_one_or_none()
        if not rid:
            return None
        return await self.get_resource(realm_id, rid)

    async def list_resources(self, realm_id: int) -> List[ResourceRead]:
        """Backward compatible list - returns all resources."""
        stmt = select(Resource).options(selectinload(Resource.external_ids)).where(Resource.realm_id == realm_id)
        result = await self.session.execute(stmt)
        resources = result.scalars().all()
        return [self._to_read(r) for r in resources]

    async def search_resources(
        self, 
        realm_id: int,
        skip: int = 0,
        limit: int = 50,
        resource_type_id: Optional[int] = None,
        external_id: Optional[str] = None,
        attributes_filter: Optional[dict] = None
    ) -> tuple[List[ResourceRead], int]:
        """Search resources with pagination and filters. Returns (items, total_count)."""
        from sqlalchemy import func
        
        # Base query
        base_stmt = select(Resource).options(selectinload(Resource.external_ids)).where(Resource.realm_id == realm_id)
        
        # Filter by resource type
        if resource_type_id is not None:
            base_stmt = base_stmt.where(Resource.resource_type_id == resource_type_id)
        
        # Filter by external_id (partial match via subquery)
        if external_id:
            subq = select(ExternalID.resource_id).where(
                ExternalID.realm_id == realm_id,
                ExternalID.external_id.ilike(f"%{external_id}%")
            )
            base_stmt = base_stmt.where(Resource.id.in_(subq))
        
        # Filter by attributes (JSONB contains)
        if attributes_filter:
            from sqlalchemy.dialects.postgresql import JSONB
            for key, value in attributes_filter.items():
                # Use @> operator for JSONB containment
                base_stmt = base_stmt.where(Resource.attributes[key].astext == str(value))
        
        # Count total
        count_stmt = select(func.count()).select_from(base_stmt.subquery())
        total = (await self.session.execute(count_stmt)).scalar() or 0
        
        # Apply pagination
        stmt = base_stmt.offset(skip).limit(limit).order_by(Resource.id)
        result = await self.session.execute(stmt)
        resources = result.scalars().all()
        
        return [self._to_read(r) for r in resources], total

    async def update_resource(self, realm_id: int, resource_id: int, resource_in: ResourceUpdate) -> Optional[ResourceRead]:
         return await self.update_resource_internal(realm_id, resource_id, resource_in)

    async def update_resource_internal(self, realm_id: int, resource_id: int, resource_in: ResourceUpdate) -> Optional[ResourceRead]:
        stmt = select(Resource).options(selectinload(Resource.external_ids)).where(Resource.realm_id == realm_id, Resource.id == resource_id)
        result = await self.session.execute(stmt)
        resource = result.scalar_one_or_none()
        if not resource:
            return None
            
        data = resource_in.model_dump(exclude_unset=True)
        
        if "external_id" in data:
            new_ext = data.pop("external_id")
            stmt_ext = select(ExternalID).where(
                ExternalID.resource_id == resource.id,
                ExternalID.realm_id == realm_id
            )
            # Should filter by Type? Usually yes.
            # Assuming primary type for external ID matches resource type
            stmt_ext = stmt_ext.where(ExternalID.resource_type_id == resource.resource_type_id)
            
            res_ext = await self.session.execute(stmt_ext)
            existing_ext = res_ext.scalar_one_or_none()
            
            if new_ext is None:
                if existing_ext:
                    await self.session.delete(existing_ext)
            else:
                if existing_ext:
                    existing_ext.external_id = new_ext
                else:
                    self.session.add(ExternalID(
                        resource_id=resource.id, 
                        realm_id=realm_id,
                        resource_type_id=resource.resource_type_id,
                        external_id=new_ext
                    ))

        if "geometry" in data:
             geo_in = data.pop("geometry")
             srid_in = data.pop("srid", None)
             if geo_in is not None:
                 resource.geometry = GeometryService.parse(geo_in, srid=srid_in)
             else:
                 resource.geometry = None

        if "attributes" in data and data["attributes"]:
             curr = dict(resource.attributes) if resource.attributes else {}
             curr.update(data["attributes"])
             resource.attributes = curr
             data.pop("attributes")

        for k, v in data.items():
            if hasattr(resource, k) and k != "srid":
                setattr(resource, k, v)
        
        await self.session.commit()
        await self.session.refresh(resource)
        
        # Need to reload external ID for read
        stmt_ext = select(ExternalID).where(ExternalID.resource_id == resource.id)
        ext = (await self.session.execute(stmt_ext)).scalar_one_or_none()
        
        return self._to_read(resource, ext.external_id if ext else None)

    async def delete_resource(self, realm_id: int, resource_id: int) -> bool:
        await self.session.execute(delete(ExternalID).where(ExternalID.resource_id == resource_id))
        
        stmt = delete(Resource).where(Resource.realm_id == realm_id, Resource.id == resource_id)
        result = await self.session.execute(stmt)
        if result.rowcount == 0:
            return False
        await self.session.commit()
        return True

    async def batch_resources(self, realm_id: int, operation: BatchResourceOperation) -> BatchResourceOperation:
        # Create
        if operation.create:
             for data in operation.create:
                 # Check existing external
                 existing_res = None
                 if data.external_id:
                     ext_stmt = select(ExternalID).where(ExternalID.realm_id == realm_id, ExternalID.external_id == data.external_id)
                     ext_res = await self.session.execute(ext_stmt)
                     ext_obj = ext_res.scalar_one_or_none()
                     if ext_obj:
                         existing_res = (await self.session.execute(select(Resource).options(selectinload(Resource.external_ids)).where(Resource.id == ext_obj.resource_id))).scalar_one_or_none()
                 
                 res_data = data.model_dump(exclude={"external_id", "geometry", "srid"})
                 res_data["attributes"] = res_data.get("attributes", {}) or {}
                 
                 geo = None
                 if data.geometry:
                     try: 
                        geo = GeometryService.parse(data.geometry, srid=data.srid)
                     except Exception as e:
                        import logging
                        logging.getLogger(__name__).error(f"Failed to parse geometry for resource {data.external_id}: {e}")
                        raise
                     
                 if existing_res:
                     if existing_res.attributes:
                         curr = dict(existing_res.attributes)
                         curr.update(res_data["attributes"])
                         existing_res.attributes = curr
                     else:
                         existing_res.attributes = res_data["attributes"]
                     
                     if geo: existing_res.geometry = geo
                     
                     self.session.add(existing_res)
                 else:
                     obj = Resource(**res_data, realm_id=realm_id, geometry=geo)
                     self.session.add(obj)
                     if data.external_id:
                         await self.session.flush()
                         self.session.add(ExternalID(resource_id=obj.id, realm_id=realm_id, resource_type_id=data.resource_type_id, external_id=data.external_id))

        if operation.update:
             for data in operation.update:
                 oid = data.id
                 ext_id = data.external_id
                 stmt = select(Resource).options(selectinload(Resource.external_ids))
                 if oid:
                     stmt = stmt.where(Resource.id == oid, Resource.realm_id == realm_id)
                 elif ext_id:
                     stmt_ext = select(ExternalID.resource_id).where(ExternalID.realm_id == realm_id, ExternalID.external_id == ext_id)
                     if data.resource_type_id: stmt_ext = stmt_ext.where(ExternalID.resource_type_id == data.resource_type_id)
                     rids = (await self.session.execute(stmt_ext)).scalars().all()
                     if not rids: continue
                     stmt = stmt.where(Resource.id == rids[0], Resource.realm_id == realm_id)
                 else: continue
                 
                 existing = (await self.session.execute(stmt)).scalar_one_or_none()
                 if existing:
                     if data.attributes:
                         curr = dict(existing.attributes) if existing.attributes else {}
                         curr.update(data.attributes)
                         existing.attributes = curr
                     if data.geometry:
                         try: existing.geometry = GeometryService.parse(data.geometry, srid=data.srid)
                         except: pass
                     # Other fields?
                     self.session.add(existing)

        if operation.delete:
             ids = []
             for item in operation.delete:
                 if isinstance(item, int): ids.append(item)
                 else:
                     stmt_ext = select(ExternalID.resource_id).where(ExternalID.realm_id == realm_id, ExternalID.external_id == item.external_id)
                     if item.resource_type_id: stmt_ext = stmt_ext.where(ExternalID.resource_type_id == item.resource_type_id)
                     rids = (await self.session.execute(stmt_ext)).scalars().all()
                     if rids: ids.append(rids[0])
                     elif item.id: ids.append(item.id)
             if ids:
                 await self.session.execute(delete(Resource).where(Resource.realm_id == realm_id, Resource.id.in_(ids)))

        await self.session.commit()
        return operation

    def _to_read(self, resource: Resource, external_id_val: Union[str, List[str], None] = None) -> ResourceRead:
        saved_geom = resource.geometry
        resource.geometry = None # temp
        
        # Load external id if not provided but exists on obj
        if external_id_val is None and getattr(resource, 'external_ids', None):
             external_id_val = [e.external_id for e in resource.external_ids]

        resp = ResourceRead.model_validate(resource)
        resp.external_id = external_id_val
        
        if saved_geom is not None:
             try:
                 sh = to_shape(saved_geom)
                 resp.geometry = shapely.geometry.mapping(sh)
             except: pass
        
        resource.geometry = saved_geom # restore
        return resp

    async def _resolve_type_id(self, realm_id: int, type_id_or_name: str) -> Optional[int]:
         try:
             return int(type_id_or_name)
         except:
             stmt = select(ResourceType.id).where(ResourceType.realm_id == realm_id, ResourceType.name == type_id_or_name)
             return (await self.session.execute(stmt)).scalar_one_or_none()
