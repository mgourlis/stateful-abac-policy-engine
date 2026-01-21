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

echo "Starting application..."
exec "$@"
