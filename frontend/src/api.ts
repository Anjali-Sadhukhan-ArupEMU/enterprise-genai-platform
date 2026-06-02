/**
 * Central API base resolver.
 *
 * - Local dev: `VITE_API_BASE_URL` is unset, so this returns the original
 *   relative path (e.g. "/api/v1/chat") and Vite's dev proxy forwards it to
 *   the FastAPI server on :8000.
 * - Production (Static Web App): `VITE_API_BASE_URL` is injected at build time
 *   (the Azure Functions base URL, e.g. https://<app>.azurewebsites.net), so
 *   calls go directly to the deployed backend.
 */
const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/+$/, "");

export function apiUrl(path: string): string {
  return `${API_BASE}${path}`;
}
