/// <reference types="vite/client" />

interface ImportMetaEnv {
  /**
   * Show or hide the sidebar Usage panel. Defaults to "true" when unset.
   * Set to "false" in frontend/.env or .env.local, then restart vite.
   */
  readonly VITE_USAGE_DASHBOARD_ENABLED?: string;
  /**
   * Base URL of the backend API (Azure Functions) in production. Unset in
   * local dev, where the Vite proxy forwards /api to the FastAPI server.
   */
  readonly VITE_API_BASE_URL?: string;
  readonly VITE_ENTRA_CLIENT_ID?: string;
  readonly VITE_ENTRA_TENANT_ID?: string;
  readonly VITE_REDIRECT_URI?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
