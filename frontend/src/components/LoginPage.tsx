/**
 * Login page — shows SSO login buttons.
 *
 * In mock mode: two buttons (Admin / User).
 * In real MSAL mode: single "Sign in with Microsoft" button.
 */
import {useAuth} from "../auth/AuthProvider";
import {isMockAuth} from "../auth/msalConfig";
import {LogoFull} from "./Logo";

export default function LoginPage() {
  const {login} = useAuth();

  return (
    <div className="flex items-center justify-center min-h-screen bg-surface">
      <div className="w-full max-w-sm mx-auto px-6">
        {/* Logo */}
        <div className="flex flex-col items-center mb-10">
          <LogoFull className="w-16 h-16 mb-4" />
          <h1 className="text-2xl font-semibold text-text-primary tracking-tight">
            GenAI Platform
          </h1>
          <p className="text-sm text-text-tertiary mt-1">Sign in to continue</p>
        </div>

        {/* Login buttons */}
        <div className="bg-surface-card rounded-2xl border border-border-light p-6 shadow-sm">
          {isMockAuth ? (
            <>
              <p className="text-xs text-text-tertiary text-center mb-4 bg-surface px-3 py-1.5 rounded-lg">
                Mock SSO — No Entra ID configured
              </p>

              <button
                onClick={() => login("admin")}
                className="w-full flex items-center justify-center gap-2 px-4 py-3 mb-3 rounded-xl bg-accent text-white text-sm font-medium hover:bg-accent-hover transition-colors duration-200 cursor-pointer"
              >
                <svg
                  width="16"
                  height="16"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <path d="M12 15a3 3 0 100-6 3 3 0 000 6z" />
                  <path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z" />
                </svg>
                Sign in as Admin
              </button>

              <button
                onClick={() => login("user")}
                className="w-full flex items-center justify-center gap-2 px-4 py-3 rounded-xl border border-border text-text-primary text-sm font-medium hover:bg-surface-hover transition-colors duration-200 cursor-pointer"
              >
                <svg
                  width="16"
                  height="16"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2" />
                  <circle cx="12" cy="7" r="4" />
                </svg>
                Sign in as User
              </button>
            </>
          ) : (
            <button
              onClick={() => login()}
              className="w-full flex items-center justify-center gap-3 px-4 py-3 rounded-xl bg-accent text-white text-sm font-medium hover:bg-accent-hover transition-colors duration-200 cursor-pointer"
            >
              {/* Microsoft logo */}
              <svg width="16" height="16" viewBox="0 0 21 21">
                <rect x="1" y="1" width="9" height="9" fill="#f25022" />
                <rect x="1" y="11" width="9" height="9" fill="#00a4ef" />
                <rect x="11" y="1" width="9" height="9" fill="#7fba00" />
                <rect x="11" y="11" width="9" height="9" fill="#ffb900" />
              </svg>
              Sign in with Microsoft
            </button>
          )}
        </div>

        <p className="text-[11px] text-text-tertiary text-center mt-6">
          Protected by Microsoft Entra ID
        </p>
      </div>
    </div>
  );
}
