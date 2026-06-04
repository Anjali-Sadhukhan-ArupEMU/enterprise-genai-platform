/**
 * Shared MSAL singleton + token helper.
 *
 * Lives in its own module so both the React AuthProvider and the plain
 * `api.ts` fetch layer can reach the same PublicClientApplication without
 * creating a circular import.
 */
import {PublicClientApplication, InteractionRequiredAuthError} from "@azure/msal-browser";
import {msalConfig, loginRequest, isMockAuth} from "./msalConfig";

export const msalInstance = new PublicClientApplication(msalConfig);

/**
 * Acquire an Entra ID token for the signed-in account, refreshing silently
 * when needed. Returns the raw id token string, or null when running in mock
 * mode or when no account is available.
 */
export async function getApiToken(): Promise<string | null> {
  if (isMockAuth) return null;

  const account = msalInstance.getActiveAccount() ?? msalInstance.getAllAccounts()[0];
  if (!account) return null;

  try {
    const result = await msalInstance.acquireTokenSilent({
      ...loginRequest,
      account,
    });
    return result.idToken ?? null;
  } catch (err) {
    // Silent refresh failed (expired session, consent needed, etc.).
    // Surface an interactive sign-in rather than sending a stale token.
    if (err instanceof InteractionRequiredAuthError) {
      await msalInstance.acquireTokenRedirect({...loginRequest, account});
    }
    return null;
  }
}
