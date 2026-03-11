from common.models import Principal

def build_unified_context(principal: Principal, req_context: dict) -> dict:
    """
    Builds a unified context dictionary for authorization checks.
    Merges principal attributes with request context.
    """
    principal_attrs = principal.attributes.copy() if principal.attributes else {}
    
    # Ensure static fields are present
    principal_attrs['id'] = principal.id
    principal_attrs['username'] = principal.username
    principal_attrs['realm_id'] = principal.realm_id

    return {
        'principal': principal_attrs,
        'context': req_context
    }
