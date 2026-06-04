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

/**
 * `fetch` wrapper that resolves the API base and attaches the Entra ID
 * bearer token (when running with real SSO). In mock mode no token is
 * added and this behaves like a plain fetch against the dev proxy.
 *
 * Pass a path beginning with `/api/...`; the base origin is prepended.
 */
export async function authFetch(
  path: string,
  init: RequestInit = {},
): Promise<Response> {
  const {getApiToken} = await import("./auth/msalInstance");
  const token = await getApiToken();

  const headers = new Headers(init.headers);
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  return fetch(apiUrl(path), {...init, headers});
}
