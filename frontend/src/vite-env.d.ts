/// <reference types="vite/client" />

interface ImportMetaEnv {
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
