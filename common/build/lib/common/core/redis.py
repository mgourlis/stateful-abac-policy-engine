from typing import Optional
import redis.asyncio as redis
import os

class RedisClient:
    _instance: Optional[redis.Redis] = None

    _loop_id: Optional[int] = None

    @classmethod
    def get_instance(cls) -> redis.Redis:
        import asyncio
        try:
            current_loop_id = id(asyncio.get_running_loop())
        except RuntimeError:
            current_loop_id = None

        if cls._instance:
            if cls._loop_id != current_loop_id:
                # Loop changed, discard old instance without closing
                # Setting to None triggers GC which tries to close on dead loop
                # Instead, we reset the pool to avoid the "Event loop is closed" error
                old_instance = cls._instance
                cls._instance = None
                cls._loop_id = None
                # Suppress the close attempt by resetting the pool reference
                try:
                    old_instance.connection_pool.reset()
                except Exception:
                    pass  # Ignore errors during cleanup
        
        if cls._instance is None:
            from common.core.config import settings
            redis_url = settings.REDIS_URL
            cls._instance = redis.from_url(redis_url, decode_responses=True)
            cls._loop_id = current_loop_id
            
        return cls._instance

    @classmethod
    async def close(cls):
        if cls._instance:
            await cls._instance.aclose()  # Use aclose() for redis-py 5.0+
            cls._instance = None
