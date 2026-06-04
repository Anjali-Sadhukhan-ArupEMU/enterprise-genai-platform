import {useEffect, useRef, useState} from "react";
import type {AvailableModel} from "../App";

interface Props {
  onNewConversation: () => void;
  userName?: string;
  isAdmin?: boolean;
  onLogout?: () => void;
  models?: AvailableModel[];
  selectedModel?: string;
  onModelChange?: (modelId: string) => void;
}

export default function Header({
  onNewConversation,
  userName,
  isAdmin,
  onLogout,
  models = [],
  selectedModel,
  onModelChange,
}: Readonly<Props>) {
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const currentModel = models.find((m) => m.model_id === selectedModel);

  // Close on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(e.target as Node)
      ) {
        setDropdownOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  return (
    <header className="flex items-center justify-between h-12 px-5 bg-surface-card border-b border-border-light">
      {/* Left: Model selector */}
      <div className="flex items-center gap-2">
        <span className="text-xs text-text-tertiary">Model</span>
        <div ref={dropdownRef} className="relative">
          <button
            onClick={() => models.length > 0 && setDropdownOpen(!dropdownOpen)}
            className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium text-text-primary bg-surface transition-all duration-200 ${
              models.length > 0
                ? "hover:bg-surface-hover cursor-pointer"
                : "cursor-default"
            }`}
          >
            {currentModel?.model_id || "Auto"}
            {models.length > 0 && (
              <svg
                width="10"
                height="10"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2.5"
                strokeLinecap="round"
                strokeLinejoin="round"
                className={`transition-transform duration-200 ${dropdownOpen ? "rotate-180" : ""}`}
              >
                <polyline points="6 9 12 15 18 9" />
              </svg>
            )}
          </button>

          {/* Dropdown menu */}
          {dropdownOpen && models.length > 0 && (
            <div className="absolute top-full left-0 mt-1.5 min-w-[180px] py-1 rounded-xl bg-surface-card border border-border-light shadow-lg z-50 animate-in fade-in slide-in-from-top-1 duration-150">
              {models.map((m) => (
                <button
                  key={m.model_id}
                  onClick={() => {
                    onModelChange?.(m.model_id);
                    setDropdownOpen(false);
                  }}
                  className={`w-full text-left px-3 py-2 text-xs transition-colors duration-150 cursor-pointer ${
                    m.model_id === selectedModel
                      ? "bg-accent/5 text-accent font-medium"
                      : "text-text-primary hover:bg-surface-hover"
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span>{m.model_id}</span>
                    {m.model_id === selectedModel && (
                      <svg
                        width="12"
                        height="12"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="2.5"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      >
                        <polyline points="20 6 9 17 4 12" />
                      </svg>
                    )}
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Right: Actions */}
      <div className="flex items-center gap-1">
        <button
          onClick={onNewConversation}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm text-text-secondary hover:bg-surface-hover hover:text-text-primary transition-colors duration-200 cursor-pointer"
        >
          <svg
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
          >
            <path d="M12 5v14M5 12h14" />
          </svg>
          New chat
        </button>

        {/* User badge */}
        {userName && (
          <span className="text-[10px] text-text-tertiary bg-surface px-2 py-0.5 rounded-full hidden sm:inline">
            {isAdmin ? "Admin" : userName}
          </span>
        )}

        {/* Sign out */}
        <button
          onClick={onLogout}
          title="Sign out"
          className="ml-1 flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs text-text-secondary hover:bg-surface-hover hover:text-text-primary transition-colors duration-200 cursor-pointer"
        >
          <svg
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4" />
            <polyline points="16 17 21 12 16 7" />
            <line x1="21" y1="12" x2="9" y2="12" />
          </svg>
          Sign out
        </button>
      </div>
    </header>
  );
}
