from .clients import (
    IStatefulABACClient, 
    HTTPStatefulABACClient, 
    DBStatefulABACClient, 
    StatefulABACClientFactory
)
from .exceptions import StatefulABACError, AuthenticationError, ApiError

from .models import Realm, Role, Principal, ResourceType, Resource, Action, ACL
from .manifest import ManifestBuilder, ConditionBuilder, Source, Operator, ContextAttribute


def StatefulABACClient(*args, **kwargs) -> IStatefulABACClient:
    """Convenience function to create a client (backwards compatible).
    
    Usage:
        client = StatefulABACClient("http://localhost:8000/api/v1")  # HTTP mode with URL
        client = StatefulABACClient(base_url="http://localhost:8000/api/v1")  # Same as above
        client = StatefulABACClient(mode="db")  # DB mode
    """
    # Handle backwards compatibility: if first positional arg looks like a URL, treat it as base_url
    if args and isinstance(args[0], str) and (args[0].startswith("http://") or args[0].startswith("https://")):
        kwargs["base_url"] = args[0]
        kwargs.setdefault("mode", "http")
        args = args[1:]  # Remove the URL from args
    
    return StatefulABACClientFactory.create(*args, **kwargs)


__all__ = [
    "IStatefulABACClient",
    "HTTPStatefulABACClient",
    "DBStatefulABACClient",
    "StatefulABACClientFactory",
    "StatefulABACClient",
    "StatefulABACError", 
    "AuthenticationError", 
    "ApiError",
    "Realm", 
    "Role", 
    "Principal", 
    "ResourceType", 
    "Resource", 
    "Action",
    "ACL",
    "ManifestBuilder",
    "ConditionBuilder",
    "Source",
    "Operator",
    "ContextAttribute"
]
