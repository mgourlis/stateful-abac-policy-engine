#!/usr/bin/env python3
"""
Initialize the Stateful ABAC Policy Engine at container startup.

This script:
1. Fetches the JWT public key from Keycloak (same approach as app-entrypoint.sh)
2. Resolves ${ENV_VAR} placeholders in the sync-tool YAML config
3. Generates a manifest JSON from the resolved config
4. Applies the manifest directly to the database (DB mode — no API needed)

Invoked by entrypoint.sh before starting the uvicorn server.
"""

import asyncio
import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

# Add SDK and common to path so DBStatefulABACClient can import them
_base = Path(__file__).resolve().parent
for pkg in ("python-sdk/src", "common"):
    p = str(_base / pkg)
    if p not in sys.path:
        sys.path.insert(0, p)

from stateful_abac_sdk import DBStatefulABACClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [init-manifest] %(levelname)s: %(message)s",
)
logger = logging.getLogger("init-manifest")

# ── Configuration ───────────────────────────────────────────────────────────

SYNC_CONFIG = os.environ.get(
    "STATEFUL_ABAC_SYNC_CONFIG",
    "/app/sync_config.yaml",
)
MANIFEST_OUTPUT = os.environ.get(
    "STATEFUL_ABAC_MANIFEST_OUTPUT",
    "/tmp/manifest.json",
)
REALM = os.environ.get("STATEFUL_ABAC_REALM", "fws-lite")

# Keycloak connection (for fetching the public key)
KC_URL = os.environ.get("KEYCLOAK_INTERNAL_URL", "http://keycloak:8080")
KC_REALM = os.environ.get("KEYCLOAK_REALM", "fws-lite")
KC_MAX_ATTEMPTS = int(os.environ.get("KC_MAX_ATTEMPTS", "30"))
KC_RETRY_DELAY = int(os.environ.get("KC_RETRY_DELAY", "2"))

# ── Keycloak public key fetching ────────────────────────────────────────────


def fetch_keycloak_public_key() -> str:
    """
    Fetch the JWT public key from Keycloak's realm endpoint.

    Retries with backoff until Keycloak is ready.
    Returns the public key string, or empty string on failure.
    """
    realm_endpoint = f"{KC_URL}/realms/{KC_REALM}"

    for attempt in range(1, KC_MAX_ATTEMPTS + 1):
        try:
            resp = urlopen(realm_endpoint, timeout=5)
            data = json.loads(resp.read().decode())
            public_key = data.get("public_key", "")
            if public_key:
                logger.info(
                    "JWT public key fetched from Keycloak (attempt %d, %d chars).",
                    attempt, len(public_key),
                )
                return public_key
            else:
                logger.warning(
                    "Keycloak responded but no public_key found in realm '%s'.",
                    KC_REALM,
                )
                return ""
        except (URLError, OSError):
            logger.info(
                "Attempt %d/%d — Keycloak not ready, retrying in %ds...",
                attempt, KC_MAX_ATTEMPTS, KC_RETRY_DELAY,
            )
            time.sleep(KC_RETRY_DELAY)
    else:
        logger.warning(
            "Keycloak did not become ready after %d attempts. "
            "Using STATEFUL_ABAC_KC_PUBLIC_KEY from env if set.",
            KC_MAX_ATTEMPTS,
        )
        return ""


# ── Env-var substitution ────────────────────────────────────────────────────

_ENV_VAR_RE = re.compile(r"\$\{([^}]+)\}")


def _resolve_env_var(match: re.Match) -> str:
    """Resolve a single ${VAR} or ${VAR:-default} placeholder."""
    expr = match.group(1)
    if ":-" in expr:
        var, default = expr.split(":-", 1)
        return os.environ.get(var.strip(), default.strip())
    return os.environ.get(expr, "")


def resolve_config(raw_yaml: str) -> str:
    """Replace all ${...} placeholders in the YAML with environment values."""
    return _ENV_VAR_RE.sub(_resolve_env_var, raw_yaml)


# ── Manifest generation ─────────────────────────────────────────────────────


def generate_manifest(config_path: Path) -> Path | None:
    """Run stateful-abac-sync to produce a manifest JSON file."""
    output_path = Path(MANIFEST_OUTPUT)

    if not config_path.exists():
        logger.warning(
            "Sync config not found at %s — skipping manifest generation.",
            config_path,
        )
        return None

    logger.info("Generating manifest from %s ...", config_path)
    result = subprocess.run(
        [
            sys.executable, "-m", "stateful_abac_sync.cli",
            "generate",
            "-c", str(config_path),
            "-o", str(output_path),
            "--indent", "2",
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        logger.error("Manifest generation failed:\n%s", result.stderr)
        if result.stdout:
            logger.error("stdout:\n%s", result.stdout)
        sys.exit(1)

    logger.info("Manifest generated at %s", output_path)
    size = output_path.stat().st_size
    logger.info("Manifest size: %.2f MB", size / (1024 * 1024))
    return output_path


# ── Manifest application ────────────────────────────────────────────────────


async def apply_manifest(manifest_path: Path) -> bool:
    """Apply manifest directly to the database (DB mode)."""
    if manifest_path is None or not manifest_path.exists():
        logger.warning("No manifest to apply.")
        return False

    logger.info("Connecting to DB (DB mode) to apply manifest...")
    client = DBStatefulABACClient(realm=REALM)

    try:
        await client.connect()
        logger.info("Applying manifest to realm '%s' (mode=replace)...", REALM)
        result = await client.apply_manifest(str(manifest_path), mode="replace")
        logger.info("Manifest applied successfully!")
        logger.info("Result: %s", json.dumps(result, indent=2, default=str))
        return True
    except Exception as exc:
        logger.error("Failed to apply manifest: %s", exc)
        return False
    finally:
        await client.close()


# ── Main ────────────────────────────────────────────────────────────────────


def main():
    logger.info("=== Stateful ABAC Initialization ===")
    logger.info("Sync config : %s", SYNC_CONFIG)
    logger.info("Manifest out: %s", MANIFEST_OUTPUT)
    logger.info("Realm       : %s", REALM)

    config_path = Path(SYNC_CONFIG)
    if not config_path.exists():
        logger.info("No sync_config.yaml — skipping initialization.")
        return

    # 1. Fetch Keycloak public key and export as env var for YAML substitution
    public_key = fetch_keycloak_public_key()
    if public_key:
        os.environ["STATEFUL_ABAC_KC_PUBLIC_KEY"] = public_key
    elif not os.environ.get("STATEFUL_ABAC_KC_PUBLIC_KEY"):
        logger.warning(
            "No public key available — the manifest will have an empty public_key. "
            "Keycloak group sync will not be able to verify JWT tokens."
        )

    # 2. Read config, resolve ${VAR} placeholders, write to temp file
    raw_config = config_path.read_text()
    resolved_config = resolve_config(raw_config)

    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".yaml",
        prefix="sync_config_resolved_",
        delete=False,
    ) as tmp:
        tmp.write(resolved_config)
        resolved_path = Path(tmp.name)

    try:
        # 3. Generate the manifest from the resolved config
        manifest_path = generate_manifest(resolved_path)

        # 4. Apply the manifest directly to the DB
        success = asyncio.run(apply_manifest(manifest_path))

        if success:
            logger.info("=== Initialization complete ===")
        else:
            logger.error("=== Initialization FAILED ===")
            sys.exit(1)
    finally:
        # Clean up the temporary resolved config
        resolved_path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
