from typing import Optional, Literal
import os

from .base import IStatefulABACClient
from .http import HTTPStatefulABACClient
from .db import DBStatefulABACClient
from ..config import settings

class StatefulABACClientFactory:
    """Factory for creating IStatefulABACClient instances."""
    
    @staticmethod
    def create(
        mode: Literal["http", "db"] = "http",
        realm: str = None,
        base_url: Optional[str] = None,
        **kwargs
    ) -> IStatefulABACClient:
        """
        Create a client with explicit configuration.
        """
        if not realm:
            raise ValueError("realm is required")
        if mode == "db":
            return DBStatefulABACClient(realm=realm)
        else:
            if not base_url:
                raise ValueError("base_url is required for HTTP mode")
                
            return HTTPStatefulABACClient(
                base_url=base_url,
                realm=realm,
                **kwargs
            )

    @staticmethod
    def from_env(**kwargs) -> IStatefulABACClient:
        """
        Create a client from environment variables (via common.core.config.settings).
        """
        mode = kwargs.pop("mode", settings.MODE)
        base_url = kwargs.pop("base_url", settings.BASE_URL)
        realm = kwargs.pop("realm", settings.REALM)
        
        return StatefulABACClientFactory.create(
            mode=mode,
            base_url=base_url,
            realm=realm,
            **kwargs
        )
