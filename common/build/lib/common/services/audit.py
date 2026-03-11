from datetime import datetime
from pydantic import BaseModel
from typing import Optional, List, Union, Callable
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession
from common.models import AuthorizationLog
from common.core.redis import RedisClient
import logging
import os
import json

logger = logging.getLogger(__name__)

class AuditEntry(BaseModel):
    realm_id: int
    principal_id: int
    action_name: str
    resource_type_name: str
    decision: bool
    resource_ids: Optional[List[Union[int, str]]] = None
    external_resource_ids: Optional[List[str]] = None

def _is_testing() -> bool:
    from common.core.config import settings
    return settings.TESTING or "pytest" in os.getenv("_", "")

async def log_authorization(entry: AuditEntry, db_session_factory: Callable[[], AsyncSession] = None):
    """
    Log authorization to Redis queue (production) or direct DB (testing/fallback).
    Falls back to direct DB write if Redis is unavailable.
    
    Args:
        entry: Audit entry data
        db_session_factory: Callable returning an async context manager for DB session (required if not using Redis or testing)
    """
    if _is_testing() and db_session_factory:
        await _write_audit_to_db(entry, db_session_factory)
        return
    
    try:
        redis_client = RedisClient.get_instance()
        
        data = entry.model_dump()
        data["timestamp"] = datetime.now().isoformat()
        
        # Use common Redis client
        await redis_client.lpush("audit_queue", json.dumps(data))
        
    except Exception as e:
        logger.warning(f"Redis audit failed, falling back to DB: {e}")
        if db_session_factory:
            await _write_audit_to_db(entry, db_session_factory)
        else:
            logger.error("Audit log failed completely (Redis failed and no DB factory provided)")

async def _write_audit_to_db(entry: AuditEntry, db_session_factory: Callable[[], AsyncSession]):
    """Direct database write for audit entries."""
    async with db_session_factory() as db:
        stmt = insert(AuthorizationLog).values(
            realm_id=entry.realm_id,
            principal_id=entry.principal_id,
            action_name=entry.action_name,
            resource_type_name=entry.resource_type_name,
            decision=entry.decision,
            resource_ids=entry.resource_ids,
            external_resource_ids=entry.external_resource_ids,
            timestamp=datetime.now()
        )
        await db.execute(stmt)
        await db.commit()

async def process_audit_queue(db_session_factory: Callable[[], AsyncSession]):
    """
    Process audit entries from Redis queue.
    """
    redis_client = RedisClient.get_instance()
    
    while True:
        try:
            result = await redis_client.brpop("audit_queue", timeout=10)
            if result:
                _, data = result
                entry = AuditEntry.model_validate_json(data)
                await _write_audit_to_db(entry, db_session_factory)
        except Exception as e:
            logger.error(f"Audit queue processing error: {e}")
            break
