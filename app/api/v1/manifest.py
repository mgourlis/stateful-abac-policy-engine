from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Dict, Any
import logging

from sqlalchemy.orm import selectinload
from common.core.database import get_db
from common.models import Realm, ResourceType, Action, AuthRole, Principal, Resource, ACL, ExternalID
from common.application.manifest_service import ManifestService

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/manifest/apply")
async def apply_manifest(
    file: UploadFile,
    mode: str = Query('update', regex='^(replace|create|update)$'),
    db: AsyncSession = Depends(get_db)
):
    """
    Apply a manifest to the system via file upload.
    
    Args:
        file: Manifest JSON file
        mode: Application mode - 'replace', 'create', or 'update'
        db: Database session
    """
    import shutil
    import uuid
    import os
    
    # Save uploaded file to temp location
    temp_filename = f"/tmp/manifest_{uuid.uuid4()}.json"
    
    try:
        # Log start of processing (this runs AFTER the upload is fully received by Uvicorn/FastAPI)
        logger.info(f"Upload received. Saving to {temp_filename}...")
        
        file_size = 0
        CHUNK_SIZE = 1024 * 1024 * 10  # 10MB
        LOG_INTERVAL = 1024 * 1024 * 100 # 100MB
        last_log_size = 0

        with open(temp_filename, "wb") as buffer:
            while True:
                chunk = await file.read(CHUNK_SIZE)
                if not chunk:
                    break
                buffer.write(chunk)
                file_size += len(chunk)
                
                if file_size - last_log_size >= LOG_INTERVAL:
                    logger.info(f"Saved {file_size / (1024*1024):.0f} MB to disk...")
                    last_log_size = file_size
            
        logger.info(f"Manifest fully saved to {temp_filename} ({file_size / (1024*1024):.2f} MB), processing...")
            
        logger.info(f"Manifest saved to {temp_filename}, processing...")
        results = await ManifestService.apply_manifest(db, temp_filename, mode=mode)
        return results
    except Exception as e:
        logger.error(f"Manifest application failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        # Cleanup
        if os.path.exists(temp_filename):
            os.remove(temp_filename)



@router.get("/realms/{realm_name}/manifest")
async def export_manifest(
    realm_name: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Export a realm's configuration as a manifest JSON.
    
    Args:
        realm_name: Name of the realm to export
    """
    try:
        manifest = await ManifestService.export_manifest(db, realm_name)
        return manifest
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Manifest export failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

