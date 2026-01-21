from typing import Annotated, Optional, Union
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from common.core.database import get_db
from common.models import Principal
from common.services.security import resolve_principal_from_token, CachedPrincipal, AnonymousPrincipal

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
oauth2_scheme_optional = OAuth2PasswordBearer(tokenUrl="token", auto_error=False)

async def get_current_principal(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> Union[Principal, CachedPrincipal]:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    principal = await resolve_principal_from_token(db, token)
    
    if isinstance(principal, AnonymousPrincipal):
        raise credentials_exception
        
    return principal

async def get_optional_current_principal(
    token: Annotated[Optional[str], Depends(oauth2_scheme_optional)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> Union[Principal, CachedPrincipal, AnonymousPrincipal]:
    if not token:
        return AnonymousPrincipal()
    return await resolve_principal_from_token(db, token)
