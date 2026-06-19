"""
Stateful ABAC SDK - Async Python SDK for Stateful ABAC Policy Engine.

Public API is resolved lazily (PEP 562) so that importing lightweight
subpackages (e.g. ``stateful_abac_sdk.manifest.builder.ManifestBuilder``)
does NOT eagerly pull in heavyweight optional dependencies such as
``common`` (sqlalchemy/asyncpg/geoalchemy2/redis/keycloak/...) that are
only required by the ``db`` client and db managers.

Heavy submodules (``clients``, ``models``, ``manifest``) are imported on
first attribute access via ``__getattr__``, preserving the historical
``from stateful_abac_sdk import <Name>`` import style. ``exceptions``
stays eager because it is lightweight and dependency-free.
"""

from importlib import import_module
from typing import TYPE_CHECKING, Any

from .exceptions import StatefulABACError, AuthenticationError, ApiError

if TYPE_CHECKING:
    # Imported only for static analysis; never imported at runtime so the
    # optional ``common`` dependency tree is not pulled in eagerly.
    from .clients import IStatefulABACClient


# Map each public name to the submodule that defines it. Lazily resolved
# via ``__getattr__`` below. Keeping this declarative makes the lazy
# surface explicit and self-documenting.
_LAZY = {
    # clients
    "IStatefulABACClient": ".clients",
    "HTTPStatefulABACClient": ".clients",
    "DBStatefulABACClient": ".clients",
    "StatefulABACClientFactory": ".clients",
    # models
    "Realm": ".models",
    "Role": ".models",
    "Principal": ".models",
    "ResourceType": ".models",
    "Resource": ".models",
    "Action": ".models",
    "ACL": ".models",
    # manifest
    "ManifestBuilder": ".manifest",
    "ConditionBuilder": ".manifest",
    "Source": ".manifest",
    "Operator": ".manifest",
    "ContextAttribute": ".manifest",
}


def __getattr__(name: str) -> Any:
    """PEP 562: lazily resolve public attributes on first access.

    This keeps ``import stateful_abac_sdk`` (and direct imports such as
    ``from stateful_abac_sdk.manifest.builder import ManifestBuilder``)
    free of the optional ``common`` dependency tree until a client/model
    is actually requested.
    """
    submodule = _LAZY.get(name)
    if submodule is None:
        raise AttributeError(f"module 'stateful_abac_sdk' has no attribute {name!r}")
    value = getattr(import_module(submodule, __name__), name)
    # Cache in module globals so subsequent accesses skip the lookup and
    # ``__getattr__`` is not called again for the same name.
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(list(globals()) + list(_LAZY) + __all__))


def StatefulABACClient(*args: Any, **kwargs: Any) -> "IStatefulABACClient":
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

    # Import lazily inside the function so merely importing this module
    # does not trigger the (optionally heavy) clients import chain.
    from .clients import StatefulABACClientFactory

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
