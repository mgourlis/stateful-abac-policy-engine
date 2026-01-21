from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncEngine
from common.core.config import settings
from typing import AsyncGenerator, Optional
import asyncio

class DatabaseManager:
    def __init__(self):
        self._engine: Optional[AsyncEngine] = None
        self._sessionmaker = None
        self._loop_id = None
        
    def _ensure_initialized(self):
        try:
            current_loop_id = id(asyncio.get_running_loop())
        except RuntimeError:
            current_loop_id = None
            
        if self._engine is None or self._loop_id != current_loop_id:
            # If loop changed, we just discard old engine reference.
            # Ideally we'd dispose it, but doing so on a different/closed loop is problematic.
            
            self._engine = create_async_engine(
                settings.DATABASE_URL,
                echo=False,
                pool_size=settings.POSTGRES_POOL_SIZE,
                max_overflow=settings.POSTGRES_MAX_OVERFLOW,
                pool_pre_ping=settings.POSTGRES_POOL_PRE_PING,
                pool_recycle=settings.POSTGRES_POOL_RECYCLE,
                pool_timeout=settings.POSTGRES_POOL_TIMEOUT,
            )
            self._sessionmaker = async_sessionmaker(self._engine, expire_on_commit=False)
            self._loop_id = current_loop_id

    @property
    def engine(self):
        self._ensure_initialized()
        return self._engine
        
    @property
    def sessionmaker(self):
        self._ensure_initialized()
        return self._sessionmaker

db_manager = DatabaseManager()

# Proxy for direct engine usage if any
class EngineProxy:
    def __getattr__(self, name):
        return getattr(db_manager.engine, name)

engine = EngineProxy()

# Proxy for AsyncSessionLocal to ensure fresh sessionmaker is used
class SessionFactoryProxy:
    def __call__(self, *args, **kwargs):
        return db_manager.sessionmaker(*args, **kwargs)

AsyncSessionLocal = SessionFactoryProxy()

async def get_db() -> AsyncGenerator:
    """Dependency for getting async session."""
    async with AsyncSessionLocal() as session:
        yield session
