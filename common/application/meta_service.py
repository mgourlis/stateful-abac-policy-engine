from typing import Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from common.models import Principal, AuthRole, Action, ResourceType

class MetaService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_acl_options(self, realm_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Return metadata for building ACL conditions in frontend.
        Includes supported operators (standard, spatial) and context sources.
        Also returns lists of principals, roles, actions, and resource types.
        """
        
        # Base lists
        principals = []
        roles = []
        actions = []
        resource_types = []
        
        # Principals
        p_stmt = select(Principal)
        if realm_id:
            p_stmt = p_stmt.where(Principal.realm_id == realm_id)
        p_res = await self.session.execute(p_stmt)
        principals = [{"id": p.id, "username": p.username} for p in p_res.scalars().all()]
        
        # Roles
        r_stmt = select(AuthRole)
        if realm_id:
            r_stmt = r_stmt.where(AuthRole.realm_id == realm_id)
        r_res = await self.session.execute(r_stmt)
        roles = [{"id": r.id, "name": r.name} for r in r_res.scalars().all()]

        # Actions
        a_stmt = select(Action)
        if realm_id:
            a_stmt = a_stmt.where(Action.realm_id == realm_id)
        a_res = await self.session.execute(a_stmt)
        actions = [{"id": a.id, "name": a.name} for a in a_res.scalars().all()]

        # Resource Types
        rt_stmt = select(ResourceType)
        if realm_id:
            rt_stmt = rt_stmt.where(ResourceType.realm_id == realm_id)
        rt_res = await self.session.execute(rt_stmt)
        resource_types = [{"id": rt.id, "name": rt.name} for rt in rt_res.scalars().all()]

        return {
            "principals": principals,
            "roles": roles,
            "actions": actions,
            "resource_types": resource_types,
            "sources": [
                {"value": "resource", "label": "Resource"},
                {"value": "principal", "label": "Principal"},
                {"value": "context", "label": "Context"}
            ],
            "operators": [
                {"value": "=", "label": "Equals (=)"},
                {"value": "!=", "label": "Not Equals (!=)"},
                {"value": "<", "label": "Less Than (<)"},
                {"value": ">", "label": "Greater Than (>)"},
                {"value": "<=", "label": "Less Than or Equal (<=)"},
                {"value": ">=", "label": "Greater Than or Equal (>=)"},
                {"value": "in", "label": "In List (in)"},
                {"value": "st_dwithin", "label": "Within Distance (st_dwithin)"},
                {"value": "st_contains", "label": "Contains (st_contains)"},
                {"value": "st_within", "label": "Within (st_within)"},
                {"value": "st_intersects", "label": "Intersects (st_intersects)"},
                {"value": "st_covers", "label": "Covers (st_covers)"}
            ],
            "context_attributes": [
                {"value": "principal.attributes", "label": "Principal Attributes"},
                {"value": "context.ip", "label": "Client IP"},
                {"value": "context.time", "label": "Request Time"}
            ]
        }
