"""
Manifest Builder Module

This module provides a fluent API for programmatically constructing
Stateful ABAC realm manifests. It enables type-safe, chainable construction
of complex authorization configurations including resources, principals,
roles, and ACL conditions.

Example:
    >>> from stateful_abac_sdk import ManifestBuilder, ConditionBuilder
    >>> 
    >>> builder = ManifestBuilder("MyRealm")
    >>> builder.add_resource_type("document")
    >>> builder.add_action("view")
    >>> builder.add_role("editor")
    >>> 
    >>> builder.add_principal("alice").with_role("editor").end()
    >>> 
    >>> builder.add_acl("document", "view") \\
    ...     .for_role("editor") \\
    ...     .when(ConditionBuilder.attr("status").eq("active")) \\
    ...     .end()
    >>> 
    >>> manifest = builder.build()
"""

from typing import Dict, Any, List, Optional, Union
import json
from .constants import Source, Operator


class FluentCondition:
    """
    Chainable condition builder for intuitive ACL condition creation.
    
    FluentCondition provides a fluent interface for building ACL conditions
    with explicit source modifiers and type-safe operators. It is created
    via `ConditionBuilder.attr(name)` and supports method chaining.
    
    Attributes:
        _attr: The attribute name to evaluate.
        _source: The source context (resource, principal, or context).
    
    Example:
        Basic equality condition::
        
            ConditionBuilder.attr("status").eq("active")
        
        Principal attribute with comparison::
        
            ConditionBuilder.attr("clearance").from_principal().gte(5)
        
        Spatial condition with distance::
        
            ConditionBuilder.attr("geometry").dwithin("$context.location", 5000)
    """
    
    def __init__(self, attr: str):
        """
        Initialize a FluentCondition for the given attribute.
        
        Args:
            attr: The name of the attribute to evaluate in conditions.
        """
        self._attr = attr
        self._source = Source.RESOURCE
    
    # Source modifiers
    def from_principal(self) -> 'FluentCondition':
        """
        Set the condition source to principal attributes.
        
        Use this when the attribute should be read from the authenticated
        principal's attributes (e.g., clearance level, department).
        
        Returns:
            Self for method chaining.
        
        Example:
            >>> ConditionBuilder.attr("clearance").from_principal().gte(5)
        """
        self._source = Source.PRINCIPAL
        return self
        
    def from_context(self) -> 'FluentCondition':
        """
        Set the condition source to request context.
        
        Use this when the attribute should be read from the authorization
        context (e.g., current time, location, IP address).
        
        Returns:
            Self for method chaining.
        
        Example:
            >>> ConditionBuilder.attr("hour").from_context().gte(9)
        """
        self._source = Source.CONTEXT
        return self
        
    def from_resource(self) -> 'FluentCondition':
        """
        Set the condition source to resource attributes (default).
        
        This is the default source. Use this explicitly when you need
        to reset after calling another source modifier.
        
        Returns:
            Self for method chaining.
        """
        self._source = Source.RESOURCE
        return self
    
    def _build(self, op: str, val: Any, args: Any = None) -> Dict[str, Any]:
        """Build the condition dictionary with the configured parameters."""
        cond = {
            "op": op,
            "attr": self._attr,
            "val": val,
            "source": self._source
        }
        if args is not None:
            cond["args"] = args
        return cond
    
    # Comparison operators
    def eq(self, val: Any) -> Dict[str, Any]:
        """
        Equal to comparison.
        
        Args:
            val: The value to compare against. Can be a literal or
                 a variable reference like "$resource.field".
        
        Returns:
            Condition dictionary ready for use in ACLs.
        """
        return self._build(Operator.EQUALS, val)
    
    def neq(self, val: Any) -> Dict[str, Any]:
        """
        Not equal to comparison.
        
        Args:
            val: The value to compare against.
        
        Returns:
            Condition dictionary ready for use in ACLs.
        """
        return self._build(Operator.NOT_EQUALS, val)
        
    def gt(self, val: Any) -> Dict[str, Any]:
        """
        Greater than comparison.
        
        Args:
            val: The value to compare against (numeric).
        
        Returns:
            Condition dictionary ready for use in ACLs.
        """
        return self._build(Operator.GREATER_THAN, val)
        
    def lt(self, val: Any) -> Dict[str, Any]:
        """
        Less than comparison.
        
        Args:
            val: The value to compare against (numeric).
        
        Returns:
            Condition dictionary ready for use in ACLs.
        """
        return self._build(Operator.LESS_THAN, val)
        
    def gte(self, val: Any) -> Dict[str, Any]:
        """
        Greater than or equal comparison.
        
        Args:
            val: The value to compare against (numeric).
        
        Returns:
            Condition dictionary ready for use in ACLs.
        """
        return self._build(Operator.GREATER_THAN_OR_EQUAL, val)
        
    def lte(self, val: Any) -> Dict[str, Any]:
        """
        Less than or equal comparison.
        
        Args:
            val: The value to compare against (numeric).
        
        Returns:
            Condition dictionary ready for use in ACLs.
        """
        return self._build(Operator.LESS_THAN_OR_EQUAL, val)
        
    def is_in(self, val: List[Any]) -> Dict[str, Any]:
        """
        Check if value is in a list.
        
        Args:
            val: List of allowed values.
        
        Returns:
            Condition dictionary ready for use in ACLs.
        
        Example:
            >>> ConditionBuilder.attr("status").is_in(["active", "pending"])
        """
        return self._build(Operator.IN, val)
    
    # Spatial operators
    def dwithin(self, val: Any, distance: float) -> Dict[str, Any]:
        """
        Spatial: check if geometry is within distance.
        
        Args:
            val: Geometry to measure distance from (WKT, GeoJSON, or
                 variable reference like "$context.location").
            distance: Maximum distance in meters.
        
        Returns:
            Condition dictionary ready for use in ACLs.
        
        Example:
            >>> ConditionBuilder.attr("geometry").dwithin("$context.location", 5000)
        """
        return self._build(Operator.ST_DWITHIN, val, args=distance)
        
    def contains(self, val: Any) -> Dict[str, Any]:
        """
        Spatial: check if geometry contains another geometry.
        
        Args:
            val: Geometry that should be contained.
        
        Returns:
            Condition dictionary ready for use in ACLs.
        """
        return self._build(Operator.ST_CONTAINS, val)
        
    def within(self, val: Any) -> Dict[str, Any]:
        """
        Spatial: check if geometry is within another geometry.
        
        Args:
            val: Geometry that should contain this one.
        
        Returns:
            Condition dictionary ready for use in ACLs.
        """
        return self._build(Operator.ST_WITHIN, val)
        
    def intersects(self, val: Any) -> Dict[str, Any]:
        """
        Spatial: check if geometry intersects another geometry.
        
        Args:
            val: Geometry to test intersection with.
        
        Returns:
            Condition dictionary ready for use in ACLs.
        """
        return self._build(Operator.ST_INTERSECTS, val)
        
    def covers(self, val: Any) -> Dict[str, Any]:
        """
        Spatial: check if geometry covers another geometry.
        
        Args:
            val: Geometry that should be covered.
        
        Returns:
            Condition dictionary ready for use in ACLs.
        """
        return self._build(Operator.ST_COVERS, val)


class ConditionBuilder:
    """
    Factory and utility class for building ACL conditions.
    
    ConditionBuilder provides two APIs:
    
    1. **Fluent API** (recommended): Start with `attr()` for chainable conditions::
    
           ConditionBuilder.attr("status").eq("active")
           ConditionBuilder.attr("clearance").from_principal().gte(5)
    
    2. **Legacy API**: Direct method calls for simple conditions::
    
           cb = ConditionBuilder()
           cb.eq("status", "active")
           cb.eq("clearance", 5, source="principal")
    
    Static methods `and_()` and `or_()` combine multiple conditions.
    
    Example:
        Complex nested condition::
        
            ConditionBuilder.and_(
                ConditionBuilder.attr("geometry").dwithin("$context.loc", 5000),
                ConditionBuilder.or_(
                    ConditionBuilder.attr("public").eq(True),
                    ConditionBuilder.attr("clearance").from_principal().gte(3)
                )
            )
    """
    
    def __init__(self):
        """Initialize a ConditionBuilder instance for legacy API usage."""
        self._conditions = {}
    
    @staticmethod
    def attr(name: str) -> FluentCondition:
        """
        Start a fluent condition chain for the given attribute.
        
        This is the recommended entry point for building conditions.
        
        Args:
            name: The attribute name to evaluate.
        
        Returns:
            A FluentCondition instance for method chaining.
        
        Example:
            >>> ConditionBuilder.attr("status").eq("active")
            >>> ConditionBuilder.attr("clearance").from_principal().gte(5)
        """
        return FluentCondition(name)
        
    @staticmethod
    def _make_leaf(op: str, attr: str, val: Any, source: str = Source.RESOURCE, args: Any = None) -> Dict[str, Any]:
        """Create a leaf condition node (internal helper)."""
        cond = {
            "op": op,
            "attr": attr,
            "val": val,
            "source": source
        }
        if args is not None:
            cond["args"] = args
        return cond

    def eq(self, attr: str, val: Any, source: str = Source.RESOURCE) -> Dict[str, Any]:
        """Legacy: Create an equality condition."""
        return self._make_leaf(Operator.EQUALS, attr, val, source)
        
    def neq(self, attr: str, val: Any, source: str = Source.RESOURCE) -> Dict[str, Any]:
        """Legacy: Create a not-equal condition."""
        return self._make_leaf(Operator.NOT_EQUALS, attr, val, source)
        
    def gt(self, attr: str, val: Any, source: str = Source.RESOURCE) -> Dict[str, Any]:
        """Legacy: Create a greater-than condition."""
        return self._make_leaf(Operator.GREATER_THAN, attr, val, source)
        
    def lt(self, attr: str, val: Any, source: str = Source.RESOURCE) -> Dict[str, Any]:
        """Legacy: Create a less-than condition."""
        return self._make_leaf(Operator.LESS_THAN, attr, val, source)
    
    def gte(self, attr: str, val: Any, source: str = Source.RESOURCE) -> Dict[str, Any]:
        """Legacy: Create a greater-than-or-equal condition."""
        return self._make_leaf(Operator.GREATER_THAN_OR_EQUAL, attr, val, source)
        
    def lte(self, attr: str, val: Any, source: str = Source.RESOURCE) -> Dict[str, Any]:
        """Legacy: Create a less-than-or-equal condition."""
        return self._make_leaf(Operator.LESS_THAN_OR_EQUAL, attr, val, source)
        
    def is_in(self, attr: str, val: List[Any], source: str = Source.RESOURCE) -> Dict[str, Any]:
        """Legacy: Create an in-list condition."""
        return self._make_leaf(Operator.IN, attr, val, source)
        
    @staticmethod
    def and_(*conditions: Dict[str, Any]) -> Dict[str, Any]:
        """
        Combine conditions with logical AND.
        
        All conditions must be true for the combined condition to be true.
        
        Args:
            *conditions: Variable number of condition dictionaries.
        
        Returns:
            Combined condition dictionary.
        
        Example:
            >>> ConditionBuilder.and_(
            ...     ConditionBuilder.attr("active").eq(True),
            ...     ConditionBuilder.attr("level").gte(5)
            ... )
        """
        return {
            "op": Operator.AND,
            "conditions": list(conditions)
        }
    
    @staticmethod
    def or_(*conditions: Dict[str, Any]) -> Dict[str, Any]:
        """
        Combine conditions with logical OR.
        
        At least one condition must be true for the combined condition to be true.
        
        Args:
            *conditions: Variable number of condition dictionaries.
        
        Returns:
            Combined condition dictionary.
        
        Example:
            >>> ConditionBuilder.or_(
            ...     ConditionBuilder.attr("public").eq(True),
            ...     ConditionBuilder.attr("owner").eq("$principal.username")
            ... )
        """
        return {
            "op": Operator.OR,
            "conditions": list(conditions)
        }
        
    def st_dwithin(self, attr: str, val: Any, distance: float, source: str = Source.RESOURCE) -> Dict[str, Any]:
        """Legacy: Create a spatial distance-within condition."""
        return self._make_leaf(Operator.ST_DWITHIN, attr, val, source, args={"distance": distance})

    def st_contains(self, attr: str, val: Any, source: str = Source.RESOURCE) -> Dict[str, Any]:
        """Legacy: Create a spatial contains condition."""
        return self._make_leaf(Operator.ST_CONTAINS, attr, val, source)

    def st_within(self, attr: str, val: Any, source: str = Source.RESOURCE) -> Dict[str, Any]:
        """Legacy: Create a spatial within condition."""
        return self._make_leaf(Operator.ST_WITHIN, attr, val, source)

    def st_intersects(self, attr: str, val: Any, source: str = Source.RESOURCE) -> Dict[str, Any]:
        """Legacy: Create a spatial intersects condition."""
        return self._make_leaf(Operator.ST_INTERSECTS, attr, val, source)

    def st_covers(self, attr: str, val: Any, source: str = Source.RESOURCE) -> Dict[str, Any]:
        """Legacy: Create a spatial covers condition."""
        return self._make_leaf(Operator.ST_COVERS, attr, val, source)


# ============================================================================
# Helper Builder Classes for Fluent Chaining
# ============================================================================

class ManifestPrincipalBuilder:
    """
    Fluent builder for configuring a principal.
    
    Returned by `ManifestBuilder.add_principal()`. Provides chainable
    methods to configure roles and attributes for a principal.
    
    Example:
        >>> builder.add_principal("alice")
        ...     .with_role("editor")
        ...     .with_role("viewer")
        ...     .with_attribute("department", "engineering")
        ...     .with_attribute("clearance", 5)
        ...     .end()  # Returns to ManifestBuilder
    
    Note:
        The principal data is added to the manifest immediately when
        `add_principal()` is called. The builder methods modify the
        existing data in-place.
    """
    
    def __init__(self, parent: 'ManifestBuilder', principal_data: Dict[str, Any]):
        """
        Initialize the principal builder.
        
        Args:
            parent: The parent ManifestBuilder to return to on `.end()`.
            principal_data: Reference to the principal dictionary in the manifest.
        """
        self._parent = parent
        self._data = principal_data
    
    def with_role(self, role_name: str) -> 'ManifestPrincipalBuilder':
        """
        Add a role to this principal.
        
        Roles define what permissions a principal has. Each role should
        be defined via `ManifestBuilder.add_role()` before being assigned.
        
        Args:
            role_name: The name of the role to assign.
        
        Returns:
            Self for method chaining.
        
        Note:
            Duplicate roles are automatically prevented.
        """
        if "roles" not in self._data:
            self._data["roles"] = []
        if role_name not in self._data["roles"]:
            self._data["roles"].append(role_name)
        return self
        
    def with_attribute(self, key: str, value: Any) -> 'ManifestPrincipalBuilder':
        """
        Add an attribute to this principal.
        
        Principal attributes can be referenced in ACL conditions using
        `.from_principal()` to enable ABAC (Attribute-Based Access Control).
        
        Args:
            key: The attribute name.
            value: The attribute value (string, number, boolean, etc.).
        
        Returns:
            Self for method chaining.
        
        Example:
            Condition using principal attribute::
            
                ConditionBuilder.attr("clearance").from_principal().gte(5)
        """
        if "attributes" not in self._data:
            self._data["attributes"] = {}
        self._data["attributes"][key] = value
        return self
        
    def end(self) -> 'ManifestBuilder':
        """
        Finish configuring this principal and return to the parent builder.
        
        Returns:
            The parent ManifestBuilder for continued chaining.
        """
        return self._parent
    
    def __getattr__(self, name):
        """Delegate unknown methods to parent (ManifestBuilder) for implicit chaining."""
        return getattr(self._parent, name)


class ManifestResourceBuilder:
    """
    Fluent builder for configuring a resource.
    
    Returned by `ManifestBuilder.add_resource()`. Provides chainable
    methods to configure attributes and geometry for a resource.
    
    Example:
        >>> builder.add_resource("doc-1", "document")
        ...     .with_attribute("classification", "secret")
        ...     .with_attribute("status", "active")
        ...     .with_geometry({"type": "Point", "coordinates": [23.7, 37.9]}, srid=4326)
        ...     .end()  # Returns to ManifestBuilder
    """
    
    def __init__(self, parent: 'ManifestBuilder', resource_data: Dict[str, Any]):
        """
        Initialize the resource builder.
        
        Args:
            parent: The parent ManifestBuilder to return to on `.end()`.
            resource_data: Reference to the resource dictionary in the manifest.
        """
        self._parent = parent
        self._data = resource_data
    
    def with_attribute(self, key: str, value: Any) -> 'ManifestResourceBuilder':
        """
        Add an attribute to this resource.
        
        Resource attributes can be referenced in ACL conditions and are
        stored in the resource's attributes dictionary.
        
        Args:
            key: The attribute name.
            value: The attribute value (string, number, boolean, etc.).
        
        Returns:
            Self for method chaining.
        
        Example:
            >>> builder.add_resource("doc-1", "document")
            ...     .with_attribute("status", "published")
            ...     .with_attribute("classification", "public")
        """
        if "attributes" not in self._data:
            self._data["attributes"] = {}
        self._data["attributes"][key] = value
        return self
        
    def with_geometry(self, geometry: Any, srid: Optional[int] = None) -> 'ManifestResourceBuilder':
        """
        Set the resource geometry for spatial queries.
        
        Geometry enables spatial ACL conditions like `.dwithin()`,
        `.contains()`, etc.
        
        Args:
            geometry: Geometry as GeoJSON dict, WKT string, or [lng, lat] list.
            srid: Optional spatial reference ID (default 4326 for WGS84).
        
        Returns:
            Self for method chaining.
        
        Example:
            GeoJSON Point::
            
                .with_geometry({"type": "Point", "coordinates": [23.7, 37.9]})
            
            WKT with SRID::
            
                .with_geometry("POINT(23.7 37.9)", srid=4326)
        """
        self._data["geometry"] = geometry
        if srid is not None:
            self._data["srid"] = srid
        return self
        
    def end(self) -> 'ManifestBuilder':
        """
        Finish configuring this resource and return to the parent builder.
        
        Returns:
            The parent ManifestBuilder for continued chaining.
        """
        return self._parent
    
    def __getattr__(self, name):
        """Delegate unknown methods to parent (ManifestBuilder) for implicit chaining."""
        return getattr(self._parent, name)


class ACLBuilder:
    """
    Fluent builder for configuring an Access Control List (ACL) entry.
    
    Returned by `ManifestBuilder.add_acl()`. Provides chainable methods
    to configure the ACL's target (role or principal) and conditions.
    
    An ACL grants a role or principal permission to perform an action
    on resources of a given type, optionally constrained by conditions.
    
    Example:
        >>> builder.add_acl("document", "view")
        ...     .for_role("editor")
        ...     .when(ConditionBuilder.attr("status").eq("active"))
        ...     .end()  # Returns to ManifestBuilder
    
    Note:
        You must specify either `for_role()` or `for_principal()` before
        calling `.end()`, otherwise a ValueError is raised.
    """
    
    def __init__(self, parent: 'ManifestBuilder', acl_data: Dict[str, Any]):
        """
        Initialize the ACL builder.
        
        Args:
            parent: The parent ManifestBuilder to return to on `.end()`.
            acl_data: Reference to the ACL dictionary in the manifest.
        """
        self._parent = parent
        self._data = acl_data
    
    def for_role(self, role_name: str) -> 'ACLBuilder':
        """
        Set the role that this ACL grants permission to.
        
        All principals with this role will receive the permission.
        
        Args:
            role_name: The name of the role.
        
        Returns:
            Self for method chaining.
        """
        self._data["role"] = role_name
        return self
        
    def for_principal(self, username: str) -> 'ACLBuilder':
        """
        Set a specific principal that this ACL grants permission to.
        
        Use this for user-specific permissions instead of role-based.
        
        Args:
            username: The username of the principal.
        
        Returns:
            Self for method chaining.
        """
        self._data["principal"] = username
        return self
        
    def for_resource(self, external_id: str) -> 'ACLBuilder':
        """
        Scope this ACL to a specific resource.
        
        By default, ACLs apply to all resources of the given type.
        Use this to limit the ACL to a single resource.
        
        Args:
            external_id: The external ID of the resource.
        
        Returns:
            Self for method chaining.
        """
        self._data["resource_external_id"] = external_id
        return self
        
    def when(self, conditions: Dict[str, Any]) -> 'ACLBuilder':
        """
        Set conditions that must be true for this ACL to grant access.
        
        Conditions enable Attribute-Based Access Control (ABAC) by
        requiring attribute comparisons to pass.
        
        Args:
            conditions: Condition dictionary from ConditionBuilder.
        
        Returns:
            Self for method chaining.
        
        Example:
            >>> builder.add_acl("document", "view")
            ...     .for_role("reader")
            ...     .when(
            ...         ConditionBuilder.and_(
            ...             ConditionBuilder.attr("status").eq("published"),
            ...             ConditionBuilder.attr("level").from_principal().gte(3)
            ...         )
            ...     )
            ...     .end()
        """
        self._data["conditions"] = conditions
        return self
        
    def end(self) -> 'ManifestBuilder':
        """
        Finish configuring this ACL and return to the parent builder.
        
        Returns:
            The parent ManifestBuilder for continued chaining.
        
        Raises:
            ValueError: If neither role, principal, nor principal_id is set.
        """
        if "role" not in self._data and "principal" not in self._data and "principal_id" not in self._data:
            raise ValueError("ACL requires either role, principal, or principal_id")
        return self._parent

    def __getattr__(self, name):
        """Delegate unknown methods to parent (ManifestBuilder) for implicit chaining."""
        return getattr(self._parent, name)


# ============================================================================
# Main ManifestBuilder
# ============================================================================

class ManifestBuilder:
    """
    Fluent builder for creating Stateful ABAC realm manifests.
    
    ManifestBuilder provides a programmatic, type-safe way to construct
    authorization manifests that can be applied to a realm. It supports
    fluent chaining and returns specialized builder objects for complex
    configurations.
    
    Attributes:
        realm_name: The name of the realm.
        description: Optional description.
        keycloak_config: Optional Keycloak integration settings.
        resource_types: List of resource type definitions.
        actions: List of action definitions.
        roles: List of role definitions.
        principals: List of principal definitions.
        resources: List of resource instances.
        acls: List of ACL entries.
    
    Example:
        Basic usage::
        
            builder = ManifestBuilder("MyRealm", description="Production realm")
            
            # Define schema
            builder.add_resource_type("document")
            builder.add_action("view")
            builder.add_action("edit")
            builder.add_role("editor")
            
            # Add principal with fluent chaining
            builder.add_principal("alice") \\
                .with_role("editor") \\
                .with_attribute("department", "legal") \\
                .end()
            
            # Add resource with geometry
            builder.add_resource("DOC-001", "document") \\
                .with_attribute("status", "active") \\
                .with_geometry({"type": "Point", "coordinates": [23.7, 37.9]}) \\
                .end()
            
            # Add conditional ACL
            builder.add_acl("document", "view") \\
                .for_role("editor") \\
                .when(ConditionBuilder.attr("status").eq("active")) \\
                .end()
            
            # Build and export
            manifest = builder.build()
            json_str = builder.to_json(indent=2)
    """
    
    def __init__(self, realm_name: str, description: Optional[str] = None):
        """
        Initialize a new ManifestBuilder.
        
        Args:
            realm_name: The name of the realm to build.
            description: Optional description of the realm.
        """
        self.realm_name = realm_name
        self.description = description
        self.keycloak_config: Optional[Dict[str, Any]] = None
        
        self.resource_types: List[Dict[str, Any]] = []
        self.actions: List[Union[str, Dict[str, Any]]] = []
        self.roles: List[Dict[str, Any]] = []
        self.principals: List[Dict[str, Any]] = []
        self.resources: List[Dict[str, Any]] = []
        self.acls: List[Dict[str, Any]] = []
        
    def set_keycloak_config(
        self,
        server_url: str,
        keycloak_realm: str,
        client_id: str,
        client_secret: Optional[str] = None,
        verify_ssl: bool = True,
        sync_cron: Optional[str] = None,
        sync_groups: bool = False,
        public_key: Optional[str] = None,
        algorithm: Optional[str] = None,
        settings: Optional[Dict[str, Any]] = None
    ) -> 'ManifestBuilder':
        """
        Configure Keycloak integration for this realm.
        
        When configured, the realm will authenticate tokens issued by
        the specified Keycloak server and can sync users/groups.
        
        Args:
            server_url: Base URL of the Keycloak server.
            keycloak_realm: Name of the Keycloak realm.
            client_id: Client ID for authentication.
            client_secret: Optional client secret.
            verify_ssl: Whether to verify SSL certificates (default True).
            sync_cron: Optional cron expression for user sync.
            sync_groups: Whether to sync Keycloak groups (default False).
            public_key: Optional RSA public key for token verification.
            algorithm: JWT algorithm (default None/RS256).
            settings: Additional Keycloak settings.
        
        Returns:
            Self for method chaining.
        
        Example:
            >>> builder.set_keycloak_config(
            ...     server_url="https://sso.example.com",
            ...     keycloak_realm="apps",
            ...     client_id="my-app",
            ...     sync_cron="0 * * * *",
            ...     sync_groups=True,
            ...     public_key="-----BEGIN PUBLIC KEY-----...",
            ...     algorithm="RS256"
            ... )
        """
        self.keycloak_config = {
            "server_url": server_url,
            "keycloak_realm": keycloak_realm,
            "client_id": client_id,
            "verify_ssl": verify_ssl,
            "sync_groups": sync_groups
        }
        if algorithm:
            self.keycloak_config["algorithm"] = algorithm
        if client_secret:
            self.keycloak_config["client_secret"] = client_secret
        if sync_cron:
            self.keycloak_config["sync_cron"] = sync_cron
        if public_key:
            self.keycloak_config["public_key"] = public_key
        if settings:
            self.keycloak_config["settings"] = settings
        return self
        
    def add_resource_type(self, name: str, is_public: bool = False) -> 'ManifestBuilder':
        """
        Add a resource type definition.
        
        Resource types categorize resources and control default access.
        Public resource types allow anonymous access by default.
        
        Args:
            name: The name of the resource type.
            is_public: If True, resources of this type are public by default.
        
        Returns:
            Self for method chaining.
        """
        self.resource_types.append({
            "name": name,
            "is_public": is_public
        })
        return self
        
    def add_action(self, name: str) -> 'ManifestBuilder':
        """
        Add an action definition.
        
        Actions represent operations that can be performed on resources
        (e.g., "view", "edit", "delete").
        
        Args:
            name: The name of the action.
        
        Returns:
            Self for method chaining.
        """
        self.actions.append(name)
        return self
        
    def add_role(self, name: str, attributes: Optional[Dict[str, Any]] = None) -> 'ManifestBuilder':
        """
        Add a role definition.
        
        Roles group permissions and can be assigned to principals.
        
        Args:
            name: The name of the role.
            attributes: Optional attributes for the role.
        
        Returns:
            Self for method chaining.
        """
        role = {"name": name}
        if attributes:
            role["attributes"] = attributes
        self.roles.append(role)
        return self
        
    def add_principal(
        self, 
        username: str, 
        roles: Optional[List[str]] = None,
        attributes: Optional[Dict[str, Any]] = None
    ) -> ManifestPrincipalBuilder:
        """
        Add a principal (user or service account).
        
        Returns a specialized builder for fluent configuration of
        roles and attributes.
        
        Args:
            username: The username or identifier of the principal.
            roles: Optional initial list of role names.
            attributes: Optional initial attributes dictionary.
        
        Returns:
            ManifestPrincipalBuilder for fluent configuration.
        
        Example:
            >>> builder.add_principal("alice") \\
            ...     .with_role("editor") \\
            ...     .with_attribute("department", "engineering") \\
            ...     .end()
        """
        user = {"username": username}
        if roles:
            user["roles"] = roles
        if attributes:
            user["attributes"] = attributes
        self.principals.append(user)
        return ManifestPrincipalBuilder(self, user)
        
    def add_resource(
        self,
        external_id: str,
        type_name: str,
        name: Optional[str] = None,
        attributes: Optional[Dict[str, Any]] = None,
        geometry: Optional[Any] = None,
        srid: Optional[int] = None
    ) -> ManifestResourceBuilder:
        """
        Add a resource instance.
        
        Returns a specialized builder for fluent configuration of
        attributes and geometry.
        
        Args:
            external_id: Unique external identifier for the resource.
            type_name: The resource type name.
            name: Optional display name (stored in attributes).
            attributes: Optional initial attributes dictionary.
            geometry: Optional geometry (GeoJSON dict or WKT string).
            srid: Optional spatial reference ID (default 4326).
        
        Returns:
            ManifestResourceBuilder for fluent configuration.
        
        Example:
            >>> builder.add_resource("DOC-001", "document") \\
            ...     .with_attribute("status", "active") \\
            ...     .with_geometry({"type": "Point", "coordinates": [23.7, 37.9]}) \\
            ...     .end()
        """
        res = {
            "external_id": external_id,
            "type": type_name
        }
        
        attrs = attributes or {}
        if name:
            attrs["name"] = name
        
        if attrs:
            res["attributes"] = attrs
            
        if geometry:
            res["geometry"] = geometry
            
        if srid is not None:
            res["srid"] = srid
            
        self.resources.append(res)
        return ManifestResourceBuilder(self, res)
        
    def add_acl(
        self,
        resource_type: str,
        action: str,
        role: Optional[str] = None,
        principal: Optional[str] = None,
        principal_id: Optional[int] = None,
        resource_external_id: Optional[str] = None,
        conditions: Optional[Dict[str, Any]] = None
    ) -> ACLBuilder:
        """
        Add an Access Control List (ACL) entry.
        
        ACLs grant permission for a role or principal to perform an
        action on resources. Returns a specialized builder for fluent
        configuration of conditions.
        
        Args:
            resource_type: The resource type this ACL applies to.
            action: The action being permitted.
            role: Optional role to grant permission to.
            principal: Optional principal username to grant permission to.
            principal_id: Optional principal ID (0 for anonymous).
            resource_external_id: Optional specific resource to scope to.
            conditions: Optional conditions from ConditionBuilder.
        
        Returns:
            ACLBuilder for fluent configuration.
        
        Example:
            >>> builder.add_acl("document", "view") \\
            ...     .for_role("editor") \\
            ...     .when(ConditionBuilder.attr("status").eq("active")) \\
            ...     .end()
        """
        acl = {
            "resource_type": resource_type,
            "action": action
        }
        
        if role:
            acl["role"] = role
        if principal:
            acl["principal"] = principal
        if principal_id is not None:
            acl["principal_id"] = principal_id
            
        if resource_external_id:
            acl["resource_external_id"] = resource_external_id
            
        if conditions:
            acl["conditions"] = conditions
            
        self.acls.append(acl)
        return ACLBuilder(self, acl)
        
    def build(self) -> Dict[str, Any]:
        """
        Construct the final manifest dictionary.
        
        Returns:
            Complete manifest as a dictionary ready for JSON serialization
            or application via the SDK.
        """
        realm_obj = {
            "name": self.realm_name
        }
        
        if self.description:
            realm_obj["description"] = self.description
            
        if self.keycloak_config:
            realm_obj["keycloak_config"] = self.keycloak_config
            
        manifest = {
            "realm": realm_obj
        }
        
        if self.resource_types:
            manifest["resource_types"] = self.resource_types
            
        if self.actions:
            manifest["actions"] = self.actions
            
        if self.roles:
            manifest["roles"] = self.roles
            
        if self.principals:
            manifest["principals"] = self.principals
            
        if self.resources:
            manifest["resources"] = self.resources
            
        if self.acls:
            manifest["acls"] = self.acls
            
        return manifest
    
    def to_json(self, **kwargs) -> str:
        """
        Serialize the manifest to a JSON string.
        
        Args:
            **kwargs: Keyword arguments passed to json.dumps()
                     (e.g., indent=2 for pretty printing).
        
        Returns:
            JSON string representation of the manifest.
        
        Example:
            >>> json_str = builder.to_json(indent=2)
            >>> with open("manifest.json", "w") as f:
            ...     f.write(json_str)
        """
        return json.dumps(self.build(), **kwargs)

