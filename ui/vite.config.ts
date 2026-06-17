import { defineConfig, loadEnv } from 'vite'
import path from 'path'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  // Resolve the project root (parent of ui/) so we can read the same .env the
  // backend uses. STATEFUL_ABAC_ROOT_PATH must match the backend's ROOT_PATH so
  // that the built UI asset URLs are prefixed the same way the app is mounted.
  const projectRoot = path.resolve(__dirname, '..')

  // Check in priority order:
  //   1. Real process env (e.g. shell export, Docker ENV)
  //   2. project-root .env (the same file the backend reads)
  //   3. ui-local .env (override)
  // loadEnv with prefix '' loads ALL vars from the .env files.
  const envFiles = {
    ...loadEnv(mode, projectRoot, ''),
    ...loadEnv(mode, process.cwd(), ''),
  }
  const rootPath = (process.env.STATEFUL_ABAC_ROOT_PATH || envFiles.STATEFUL_ABAC_ROOT_PATH || '').trim()
  // Vite wants a base like '/policy-engine/' (trailing slash) or '/' when empty.
  const base = rootPath ? `${rootPath.replace(/\/$/, '')}/` : '/'

  if (rootPath) {
    console.log(`[vite] Using base '${base}' from STATEFUL_ABAC_ROOT_PATH`)
  }

  return {
    base,
    plugins: [react()],
    server: {
      port: 5173,
      proxy: {
        // Proxy API calls to the backend; prefix both the stripped and prefixed forms.
        '/api': {
          target: 'http://localhost:8000',
          changeOrigin: true,
        },
        ...(rootPath ? { [`${base}api`]: {
          target: 'http://localhost:8000',
          changeOrigin: true,
          rewrite: (p: string) => p.replace(new RegExp(`^${base}api`), '/api'),
        } } : {}),
      },
    },
    build: {
      outDir: 'dist',
      emptyOutDir: true,
    },
  }
})
