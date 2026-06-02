/**
 * MSAL configuration for Azure Entra ID authentication.
 *
 * When VITE_ENTRA_CLIENT_ID is not set, uses a mock auth flow
 * that simulates login locally (no real Entra needed).
 */
import {Configuration, LogLevel} from "@azure/msal-browser";

const clientId = import.meta.env.VITE_ENTRA_CLIENT_ID || "";
const tenantId = import.meta.env.VITE_ENTRA_TENANT_ID || "";
const redirectUri = import.meta.env.VITE_REDIRECT_URI || window.location.origin;

export const isMockAuth = !clientId;

export const msalConfig: Configuration = {
  auth: {
    clientId: clientId || "00000000-0000-0000-0000-000000000000",
    authority: tenantId
      ? `https://login.microsoftonline.com/${tenantId}`
      : "https://login.microsoftonline.com/common",
    redirectUri,
  },
  cache: {
    cacheLocation: "sessionStorage",
  },
  system: {
    loggerOptions: {
      logLevel: LogLevel.Warning,
      loggerCallback: (level, message) => {
        if (level === LogLevel.Error) console.error(message);
      },
    },
  },
};

export const loginRequest = {
  scopes: ["User.Read", "openid", "profile", "email"],
};
