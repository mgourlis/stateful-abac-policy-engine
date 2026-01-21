# Stateful ABAC Policy Engine - Admin UI

A modern, React-based administration interface for the Stateful ABAC Policy Engine. This UI allows administrators to manage Realms, Resources, Roles, Principals, and Access Control Lists (ACLs) with an intuitive user experience.

## ✨ Features

### 🏛️ Realm Management
- **Dashboard**: Overview of realm statistics.
- **Resource Types**: Create and manage resource schemas.
- **Roles & Principals**: Manage authentication roles and users/principals.
- **Actions**: Define available actions for permissions.

### 📦 Resource Management
- **Advanced Search**: Filter resources by Type, External ID, and arbitrary Attributes (JSON).
- **Pagination**: Efficiently browse large datasets.
- **Inspection**: View detailed resource attributes and metadata.

### 🛡️ ACL Management
- **Visual Condition Builder**: Create complex ABAC conditions without writing JSON.
  - Supports nested `AND`/`OR` groups.
  - Variable references (`$principal`, `$context`, `$resource`).
  - Spatial operators (`st_dwithin`, `st_contains`, etc.).
- **Unified Creation Flow**: Context-aware ACL creation from Resource or Resource Type screens.
- **Type-Level ACLs**: efficient permissions for entire classes of resources.

## 🚀 Getting Started

### Prerequisites
- Node.js 20+
- Stateful ABAC Policy Engine API running locally on port `8000` (for development proxy)

### Local Development

1. **Install Dependencies**
   ```bash
   cd ui
   npm install
   ```

2. **Start Development Server**
   ```bash
   npm run dev
   ```
   The UI will be available at `http://localhost:5173`.
   API requests are proxied to `http://localhost:8000`.

### 🏗️ Build for Production

To build the static assets for production deployment:

```bash
npm run build
```

This generates the `dist/` directory containing the optimized application.

## 🔌 Integration with Backend

The Stateful ABAC Policy Engine Python backend is configured to serve this UI automatically when enabled.

### 1. File Structure
The backend expects the build artifacts to be located at `ui/dist` relative to the project root.

### 2. Configuration
Ensure the `ENABLE_UI` environment variable is set to true in your backend configuration (or `.env` file):

```env
STATEFUL_ABAC_ENABLE_UI=true
```

### 3. Serving
When the backend starts with `ENABLE_UI=true`, it mounts:
- `/assets` -> `ui/dist/assets`
- `/*` -> serves `ui/dist/index.html` (SPA Fallback)

## 🐳 Docker Deployment

The recommended way to run the UI in Docker is via **Docker Compose**.

### Option 1: Bundled Service (Recommended for Demo)
To run the backend and UI as a single service:
```bash
docker compose up app-bundled
```
Access the UI at `http://localhost:8000`.

### Option 2: Development Mode (Hot Reload)
To run the backend and UI with live code reloading:
```bash
docker compose --profile ui up
```
Access the UI at `http://localhost:5173`.

### Option 3: Manual Build
If you prefer building the image manually using `Dockerfile.withui`:

1. **Build the Image** from the project root:
   ```bash
   docker build -f Dockerfile.withui -t stateful-abac-app-ui .
   ```

2. **Run the Container**:
   ```bash
   docker run -p 8000:8000 -e STATEFUL_ABAC_ENABLE_UI=true stateful-abac-app-ui
   ```

Access the UI at `http://localhost:8000`.

## 🛠️ Tech Stack
- **Framework**: React 18 + TypeScript
- **Build Tool**: Vite
- **State Management**: React Query (TanStack Query)
- **Styling**: Vanilla CSS (Variables & Utility Classes)
- **Icons**: Lucide React
