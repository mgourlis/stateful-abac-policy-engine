"""
Manifest export functionality for SDK.
The apply logic now lives on the backend in app/services/manifest_service.py
"""
import logging

logger = logging.getLogger(__name__)

async def export_manifest(client, realm_name: str):
    """
    Export a realm's configuration as a manifest JSON.
    
    Args:
        client: StatefulABACClient instance
        realm_name: Name of the realm to export
        
    Returns:
        Manifest dictionary
    """
    # Use the backend API endpoint for export
    manifest = await client.request("GET", f"/realms/{realm_name}/manifest")
    return manifest
