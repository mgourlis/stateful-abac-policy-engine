FROM python:3.12-slim

WORKDIR /app

# Install system dependencies for psycopg/asyncpg and geospatial libs
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    libgeos-dev \
    libproj-dev \
    && rm -rf /var/lib/apt/lists/*

# Install poetry
RUN pip install poetry

# Copy dependency files first for better caching
COPY pyproject.toml poetry.lock* ./

# Copy common package (required for path dependency)
COPY common ./common

# Configure poetry to not create virtual env (we're in a container)
RUN poetry config virtualenvs.create false

# Install dependencies
RUN poetry install --only main --no-root --no-interaction --no-ansi

# Copy application code
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./

# Copy and set up entrypoint
COPY entrypoint.sh ./
RUN chmod +x entrypoint.sh

# Default port
EXPOSE 8000

ENTRYPOINT ["./entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

