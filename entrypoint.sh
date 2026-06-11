#!/bin/bash
set -e

echo "Waiting for database to be ready..."
# Wait for the database to be available
while ! python -c "import asyncio; import asyncpg; asyncio.run(asyncpg.connect('$STATEFUL_ABAC_DATABASE_URL'.replace('postgresql+asyncpg://', 'postgresql://')))" 2>/dev/null; do
    echo "Database not ready, waiting..."
    sleep 2
done
echo "Database is ready!"

echo "Running Alembic migrations..."
alembic upgrade head
echo "Migrations complete!"

# ── Initialize realm from sync config (if present) ──────────────────────────
if [ -f /app/sync_config.yaml ]; then
    echo "sync_config.yaml found — initializing realm via DB mode..."
    python3 /app/init_manifest.py
else
    echo "No sync_config.yaml — skipping manifest initialization."
fi
# ────────────────────────────────────────────────────────────────────────────

echo "Starting application..."
exec "$@"
