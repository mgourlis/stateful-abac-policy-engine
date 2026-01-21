from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from app.api.deps import get_current_principal, get_db
from common.application.meta_service import MetaService
import logging
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/meta/acl-options", response_model=Dict[str, Any])
async def get_acl_metadata(realm_id: Optional[int] = None, db: AsyncSession = Depends(get_db)):
    """
    Return metadata for building ACL conditions in frontend.
    Includes supported operators (standard, spatial) and context sources.
    Also returns lists of principals, roles, actions, and resource types.
    """
    service = MetaService(db)
    return await service.get_acl_options(realm_id)
