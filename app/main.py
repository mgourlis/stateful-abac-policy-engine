from fastapi import FastAPI
from contextlib import asynccontextmanager
import logging
import asyncio
import os
from common.worker import SchedulerWorker
from common.core.config import settings
from common.core.database import AsyncSessionLocal

# Configure logging to show INFO logs from the application
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    force=True  # Remove any existing handlers to prevent duplicates
)
from app.api.v1.auth import router as auth_router
from app.api.v1.realms import router as realms_router
from app.api.v1.meta import router as meta_router
from app.api.v1.manifest import router as manifest_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    # Start audit queue processor in production only
    audit_task = None
    if not settings.TESTING:
        from common.services.audit import process_audit_queue
        # Pass the session factory explicitly
        audit_task = asyncio.create_task(process_audit_queue(AsyncSessionLocal))
        
    # Start Scheduler if enabled (defaulting to True for convenience unless explicitly disabled)
    # This restores "start from main" capability while keeping the code decoupled in common/worker.py
    worker_instance = None
    if settings.ENABLE_SCHEDULER and not settings.TESTING:
        worker_instance = SchedulerWorker()
        await worker_instance.start_scheduler()
    
    yield
    
    # Shutdown
    # Close Redis connection first
    from common.core.redis import RedisClient
    await RedisClient.close()
    
    if audit_task:
        audit_task.cancel()
        try:
            await audit_task
        except asyncio.CancelledError:
            pass
            
    # Shutdown Scheduler
    if worker_instance:
        await worker_instance.stop_scheduler()

tags_metadata = [
    {
        "name": "auth",
        "description": "Authentication and Token management.",
    },
    {
        "name": "realms",
        "description": "Realm management, including Keycloak synchronization and Entity CRUD (Roles, Resources, ACLs).",
    },
]

app = FastAPI(
    title="Stateful ABAC Policy Engine",
    description="Authentication and Authorization Service with Keycloak Integration.",
    version="1.0.0",
    openapi_tags=tags_metadata,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)

app.include_router(auth_router, prefix="/api/v1", tags=["auth"])
app.include_router(realms_router, prefix="/api/v1", tags=["realms"])
app.include_router(meta_router, prefix="/api/v1", tags=["meta"])
app.include_router(manifest_router, prefix="/api/v1", tags=["manifest"])

# Optional UI serving - must be AFTER all API routes
if settings.ENABLE_UI:
    import os
    ui_dist_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "ui", "dist")
    if os.path.isdir(ui_dist_path):
        from fastapi.staticfiles import StaticFiles
        from fastapi.responses import FileResponse
        
        # Serve static assets
        app.mount("/assets", StaticFiles(directory=os.path.join(ui_dist_path, "assets")), name="ui-assets")
        
        # SPA fallback for client-side routing
        @app.get("/{full_path:path}")
        async def serve_spa(full_path: str):
            # Don't catch API routes
            if full_path.startswith("api/"):
                return {"detail": "Not Found"}
            file_path = os.path.join(ui_dist_path, full_path)
            if os.path.isfile(file_path):
                return FileResponse(file_path)
            return FileResponse(os.path.join(ui_dist_path, "index.html"))
else:
    @app.get("/")
    async def root():
        return {"message": "Stateful ABAC Policy Engine Running"}
