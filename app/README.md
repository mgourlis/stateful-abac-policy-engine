# Stateful ABAC Policy Engine - Backend Service

This directory contains the source code for the FastAPI backend service.

## 📂 Structure

- **`api/`**: API Route handlers (Realms, Auth, Resources).
- **`main.py`**: Application entry point.

*Note: Core logic, database models, and shared utilities are located in the top-level `common/` directory.*

## 🚀 Running the API

The application is designed to be run from the **project root** directory.

### 1. Install Dependencies
```bash
# From project root (../)
poetry install
```

### 2. Configure Environment
Ensure you have a `.env` file in the project root (see `../.env.example` or default values).

### 3. Start Database & Redis
The app requires PostgreSQL (with PostGIS) and Redis.
```bash
docker compose up -d db cache
```

### 4. Run Migrations
Apply database schema:
```bash
poetry run alembic upgrade head
```

### 5. Start Server
```bash
poetry run uvicorn app.main:app --reload --port 8000
```
- **API Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **Health Check**: [http://localhost:8000/](http://localhost:8000/)

## 🧪 Running Tests

```bash
# Run all tests
poetry run pytest

# Run specific test file
poetry run pytest tests/test_abac_flow.py
```

## 🐳 Docker Deployment

To build and run the backend service *without* the UI (for API-only deployments):

### 1. Build Image
```bash
docker build -t stateful-abac-app .
```

### 2. Run Container
```bash
docker run -p 8000:8000 \
  --env-file .env \
  stateful-abac-app
```
*(Ensure your `.env` contains database and redis configuration reachable from within the container)*

### 🚀 Build & Run with UI

To build a unified image containing both the Backend and the Frontend (served statically):

#### 1. Build
```bash
docker build -f Dockerfile.withui -t stateful-abac-app-ui .
```

#### 2. Run
```bash
docker run -p 8000:8000 \
  --env-file .env \
  -e STATEFUL_ABAC_ENABLE_UI=true \
  stateful-abac-app-ui
```
*Access the UI at http://localhost:8000*
