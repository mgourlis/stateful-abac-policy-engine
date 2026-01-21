
import sys
from pathlib import Path
import json

# Add SDK to path
sdk_path = Path(__file__).resolve().parent.parent / "python-sdk" / "src"
sys.path.append(str(sdk_path))

from stateful_abac_sdk import ManifestBuilder, ConditionBuilder

def debug_manifest():
    realm_name = "DebugRealm"
    builder = ManifestBuilder(realm_name)
    cb = ConditionBuilder
    
    # Replicate failing condition
    (builder.resource("FAC-HQ", "facility")
            .End())
            
    builder.acl("facility", "enter", role="security_officer").when(
        cb.and_(
            cb.prop("geometry").dwithin("$context.current_location", 100),
            cb.or_(
                cb.prop("clearance").of_source("principal").gte("$resource.min_clearance"),
                cb.prop("category").eq("standard")
            ),
            cb.prop("hour").of_source("context").gte(6),
            cb.prop("hour").of_source("context").lte(22)
        )
    ).End()
    
    print(json.dumps(builder.build(), indent=2))

if __name__ == "__main__":
    debug_manifest()
