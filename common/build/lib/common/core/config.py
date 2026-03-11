import os
from typing import Optional

class Config:
    @property
    def REDIS_URL(self) -> str:
        return os.getenv("STATEFUL_ABAC_REDIS_URL", "redis://localhost:6379")

    @property
    def JWT_SECRET_KEY(self) -> str:
        return os.getenv("STATEFUL_ABAC_JWT_SECRET_KEY", "changeme")

    @property
    def JWT_ALGORITHM(self) -> str:
        return os.getenv("STATEFUL_ABAC_JWT_ALGORITHM", "HS256")

    @property
    def DATABASE_URL(self) -> str:
        return os.getenv("STATEFUL_ABAC_DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost/demo-auth-db")

    @property
    def TESTING(self) -> bool:
        return os.getenv("STATEFUL_ABAC_TESTING", "").lower() == "true"

    @property
    def ENABLE_SCHEDULER(self) -> bool:
        return os.getenv("STATEFUL_ABAC_ENABLE_SCHEDULER", "true").lower() == "true"

    @property
    def POSTGRES_POOL_SIZE(self) -> int:
        return int(os.getenv("STATEFUL_ABAC_POSTGRES_POOL_SIZE", "50"))

    @property
    def POSTGRES_MAX_OVERFLOW(self) -> int:
        return int(os.getenv("STATEFUL_ABAC_POSTGRES_MAX_OVERFLOW", "50"))

    @property
    def POSTGRES_POOL_RECYCLE(self) -> int:
        return int(os.getenv("STATEFUL_ABAC_POSTGRES_POOL_RECYCLE", "300"))

    @property
    def POSTGRES_POOL_TIMEOUT(self) -> int:
        return int(os.getenv("STATEFUL_ABAC_POSTGRES_POOL_TIMEOUT", "30"))

    @property
    def POSTGRES_POOL_PRE_PING(self) -> bool:
        return os.getenv("STATEFUL_ABAC_POSTGRES_POOL_PRE_PING", "true").lower() == "true"

    @property
    def ENABLE_UI(self) -> bool:
        """Enable serving the React UI from /ui/dist if it exists."""
        return os.getenv("STATEFUL_ABAC_ENABLE_UI", "false").lower() == "true"

settings = Config()
