import os
from typing import Optional

from dotenv import load_dotenv

# Load .env once when the config module is first imported.
# override=False so real environment variables (e.g. Docker-injected ones) always win
# over .env values. When there is no .env (e.g. inside a container) this is a no-op.
load_dotenv(override=False)

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

    @property
    def ROOT_PATH(self) -> str:
        """Deployment sub-path prefix for the app (e.g. '/policy-engine').

        Supports two deployment modes from a single setting:
          * Reverse proxy (Nginx/Apache): the prefix is advertised to OpenAPI
            (correct docs/SDK URLs) while requests still route at /api/v1/...
            whether or not the proxy strips the prefix.
          * Standalone: the app is directly reachable at /ROOT_PATH/api/v1/...

        Empty string (default) keeps the current root-mounted behaviour.
        A leading '/' is enforced and any trailing '/' is stripped.
        """
        val = os.getenv("STATEFUL_ABAC_ROOT_PATH", "").strip()
        if val and not val.startswith("/"):
            val = "/" + val
        return val.rstrip("/")

settings = Config()
