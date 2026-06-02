/**
 * Auth context that works with both real MSAL and mock auth.
 *
 * Provides user info (name, email, role, token) to the entire app.
 * When Entra is not configured, shows a local login screen where
 * the user picks "Admin" or "User" role.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import type {ReactNode} from "react";
import {MsalProvider, useMsal, useIsAuthenticated} from "@azure/msal-react";
import {PublicClientApplication, InteractionStatus} from "@azure/msal-browser";
import {msalConfig, loginRequest, isMockAuth} from "./msalConfig";

/* ── Types ──────────────────────────────────────────────────────────── */

export interface AuthUser {
  userId: string;
  name: string;
  email: string;
  roles: string[];
  isAdmin: boolean;
}

interface AuthContextValue {
  user: AuthUser | null;
  isLoading: boolean;
  login: (role?: "admin" | "user") => void;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue>({
  user: null,
  isLoading: true,
  login: () => {},
  logout: () => {},
});

export const useAuth = () => useContext(AuthContext);

/* ── Mock Auth (no Entra configured) ────────────────────────────────── */

const MOCK_USERS: Record<string, AuthUser> = {
  admin: {
    userId: "admin-001",
    name: "Admin User",
    email: "admin@contoso.com",
    roles: ["admin"],
    isAdmin: true,
  },
  user: {
    userId: "user-001",
    name: "Standard User",
    email: "user@contoso.com",
    roles: ["user"],
    isAdmin: false,
  },
};

function MockAuthProvider({children}: {children: ReactNode}) {
  const [user, setUser] = useState<AuthUser | null>(() => {
    const saved = sessionStorage.getItem("mock_user");
    return saved ? JSON.parse(saved) : null;
  });

  const login = useCallback((role: "admin" | "user" = "user") => {
    const u = MOCK_USERS[role];
    sessionStorage.setItem("mock_user", JSON.stringify(u));
    setUser(u);
  }, []);

  const logout = useCallback(() => {
    sessionStorage.removeItem("mock_user");
    setUser(null);
  }, []);

  const value = useMemo(
    () => ({user, isLoading: false, login, logout}),
    [user, login, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

/* ── Real MSAL Auth ─────────────────────────────────────────────────── */

const msalInstance = new PublicClientApplication(msalConfig);

function MsalAuthInner({children}: {children: ReactNode}) {
  const {instance, accounts, inProgress} = useMsal();
  const isAuthenticated = useIsAuthenticated();
  const [user, setUser] = useState<AuthUser | null>(null);

  useEffect(() => {
    if (isAuthenticated && accounts.length > 0) {
      const account = accounts[0];
      const roles = (account.idTokenClaims?.roles as string[]) || ["user"];
      setUser({
        userId: account.localAccountId,
        name: account.name || "",
        email: account.username || "",
        roles,
        isAdmin: roles.includes("admin"),
      });
    } else {
      setUser(null);
    }
  }, [isAuthenticated, accounts]);

  const login = useCallback(() => {
    instance.loginRedirect(loginRequest);
  }, [instance]);

  const logout = useCallback(() => {
    instance.logoutRedirect();
  }, [instance]);

  const isLoading = inProgress !== InteractionStatus.None;

  const value = useMemo(
    () => ({user, isLoading, login, logout}),
    [user, isLoading, login, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

/* ── Exported Provider (auto-selects mock vs real) ──────────────────── */

export function AuthProvider({children}: {children: ReactNode}) {
  if (isMockAuth) {
    return <MockAuthProvider>{children}</MockAuthProvider>;
  }

  return (
    <MsalProvider instance={msalInstance}>
      <MsalAuthInner>{children}</MsalAuthInner>
    </MsalProvider>
  );
}
