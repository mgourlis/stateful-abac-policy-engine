from typing import Optional, Union, Dict
from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from jose import JWTError, jwt
from common.core.config import settings
from common.models import Principal
from common.services.cache import CacheService

class CachedPrincipal:
    """Principal-like object created from cached data."""
    def __init__(self, data: dict):
        self.id = data["id"]
        self.username = data["username"]
        self.realm_id = data["realm_id"]
        self.attributes = data.get("attributes", {})
        self.role_ids = data.get("role_ids", [])

class AnonymousPrincipal:
    def __init__(self):
        self.id = 0
        self.username = "anonymous"
        self.realm_id = 0
        self.attributes = {"is_anonymous": True}
        self.role_ids = []

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Create a JWT access token.
    Uses common configuration for Secret Key and Algorithm.
    """
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return encoded_jwt

async def resolve_principal_from_token(
    db: AsyncSession,
    token: Optional[str],
    realm_context: Optional[str] = None
) -> Union[Principal, CachedPrincipal, AnonymousPrincipal]:
    """
    Resolve a Principal from a JWT token.
    Uses cached data if available to avoid DB lookups.
    """
    if token:
        try:           
            # Determine Key and Algorithm
            verify_key = settings.JWT_SECRET_KEY
            verify_algo = settings.JWT_ALGORITHM
            realm_id = None
            
            effective_realm = realm_context
            
            if effective_realm:
                try:
                    realm_map = await CacheService.get_realm_map(effective_realm, db)
                    realm_id = int(realm_map["_id"])
                    if "_public_key" in realm_map:
                        verify_key = realm_map["_public_key"]
                        if "-----BEGIN PUBLIC KEY-----" not in verify_key:
                            verify_key = f"-----BEGIN PUBLIC KEY-----\n{verify_key}\n-----END PUBLIC KEY-----"
                    
                    if "_algorithm" in realm_map:
                        verify_algo = realm_map["_algorithm"]
                except ValueError:
                    pass
            
            # Verify with selected key
            payload = jwt.decode(token, verify_key, algorithms=[verify_algo], options={"verify_aud": False})
            sub = payload.get("sub")
            # Realm in token claims takes precedence over context
            token_realm = payload.get("realm")
            if token_realm:
                effective_realm = token_realm
                try:
                    realm_map = await CacheService.get_realm_map(effective_realm, db)
                    realm_id = int(realm_map["_id"])
                except ValueError:
                    pass
            
            if sub:
                # Try lookup from cache
                principal_data = None
                
                # Use preferred_username if available (Keycloak standard claim)
                username = payload.get("preferred_username") or sub
                
                try:
                    principal_id = int(sub)
                    principal_data = await CacheService.get_principal(principal_id=principal_id, db_session=db)
                except ValueError:
                    # sub is not an ID - use preferred_username or sub as username
                    if realm_id:
                        principal_data = await CacheService.get_principal(username=username, realm_id=realm_id, db_session=db)
                
                if principal_data:
                    # Extract roles from token - check multiple sources:
                    # 1. realm_access.roles (Keycloak realm roles)
                    # 2. roles (top-level roles if present)
                    # 3. groups (Keycloak groups, often have paths like "/admin")
                    token_roles = set()
                    
                    realm_roles = payload.get("realm_access", {}).get("roles", [])
                    if realm_roles:
                        token_roles.update(realm_roles)
                    
                    top_roles = payload.get("roles", [])
                    if top_roles:
                        token_roles.update(top_roles)
                    
                    groups = payload.get("groups", [])
                    if groups:
                        token_roles.update(g.lstrip("/") for g in groups)
                    
                    if token_roles:
                        principal_data["token_roles"] = list(token_roles)
                    
                    return CachedPrincipal(principal_data)
                    
        except (JWTError, ValueError):
            pass
            
    return AnonymousPrincipal()
