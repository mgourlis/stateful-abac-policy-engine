"""
Constants/Enums for Manifest and Realm configuration.
Mirrors app/api/v1/meta.py
"""
from enum import Enum

class Source(str, Enum):
    RESOURCE = "resource"
    PRINCIPAL = "principal"
    CONTEXT = "context"

class Operator(str, Enum):
    # Standard
    EQUALS = "="
    NOT_EQUALS = "!="
    LESS_THAN = "<"
    GREATER_THAN = ">"
    LESS_THAN_OR_EQUAL = "<="
    GREATER_THAN_OR_EQUAL = ">="
    IN = "in"
    
    # Logical
    AND = "and"
    OR = "or"
    
    # Spatial
    ST_DWITHIN = "st_dwithin"
    ST_CONTAINS = "st_contains"
    ST_WITHIN = "st_within"
    ST_INTERSECTS = "st_intersects"
    ST_COVERS = "st_covers"

class ContextAttribute(str, Enum):
    PRINCIPAL_ATTRIBUTES = "principal.attributes"
    CLIENT_IP = "context.ip"
    REQUEST_TIME = "context.time"

