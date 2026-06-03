import {LogoFull, LogoIcon} from "./Logo";
import UsageDashboard from "./UsageDashboard";

type ChatMode = "quick" | "deep" | "code" | "creative";

interface ConversationItem {
  id: string;
  title: string;
}

interface Props {
  mode: ChatMode;
  onModeChange: (mode: ChatMode) => void;
  collapsed: boolean;
  onToggle: () => void;
  conversations: ConversationItem[];
  activeConversationId: string | null;
  onSelectConversation: (id: string) => void;
  onNewConversation: () => void;
  isAdmin?: boolean;
  currentView?: "chat" | "admin";
  onViewChange?: (view: "chat" | "admin") => void;
  usageRefreshKey?: number;
}

const MODES: {id: ChatMode; label: string; desc: string}[] = [
  {id: "quick", label: "Quick", desc: "Fast answers"},
  {id: "deep", label: "Deep", desc: "Thorough analysis"},
  {id: "code", label: "Code", desc: "Technical tasks"},
  {id: "creative", label: "Creative", desc: "Ideation"},
];

export default function Sidebar({
  mode,
  onModeChange,
  collapsed,
  onToggle,
  conversations,
  activeConversationId,
  onSelectConversation,
  onNewConversation,
  isAdmin,
  currentView,
  onViewChange,
  usageRefreshKey = 0,
}: Props) {
  const adminLabel = currentView === "admin" ? "Back to Chat" : "Admin Panel";
  return (
    <aside
      className={`flex flex-col h-full bg-sidebar-bg transition-all duration-300 ease-in-out ${
        collapsed ? "w-16" : "w-72"
      }`}
    >
      {/* Logo + New Chat */}
      <div className="flex items-center justify-between px-3 h-12 border-b border-sidebar-border">
        {!collapsed ? (
          <div className="flex items-center gap-2.5">
            <LogoFull className="w-7 h-7" />
            <span className="text-sm font-semibold text-white tracking-tight">
              GenAI Platform
            </span>
          </div>
        ) : (
          <LogoIcon className="w-6 h-6 mx-auto" />
        )}
        {!collapsed && (
          <button
            onClick={onNewConversation}
            className="p-1.5 rounded-lg hover:bg-sidebar-hover transition-colors duration-200 text-sidebar-text-muted hover:text-white cursor-pointer"
            aria-label="New conversation"
          >
            <svg
              width="18"
              height="18"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
            >
              <path d="M12 5v14M5 12h14" />
            </svg>
          </button>
        )}
      </div>

      {/* Mode Selector */}
      {!collapsed && (
        <div className="px-3 py-3">
          <div className="grid grid-cols-4 gap-1 p-1 bg-sidebar-hover rounded-xl">
            {MODES.map((m) => (
              <button
                key={m.id}
                onClick={() => onModeChange(m.id)}
                className={`px-2 py-1.5 rounded-lg text-xs font-medium text-center transition-all duration-200 cursor-pointer ${
                  mode === m.id
                    ? "bg-sidebar-bg text-white shadow-sm"
                    : "text-sidebar-text-muted hover:text-sidebar-text"
                }`}
                title={m.desc}
              >
                {m.label}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Conversation History */}
      <div className="flex-1 overflow-y-auto px-2 py-1">
        {!collapsed && conversations.length > 0 && (
          <p className="text-[11px] font-medium text-sidebar-text-muted uppercase tracking-wider mb-2 px-2">
            Recent
          </p>
        )}
        {conversations.map((conv) => (
          <button
            key={conv.id}
            onClick={() => onSelectConversation(conv.id)}
            className={`w-full text-left px-2.5 py-2 rounded-xl text-sm transition-all duration-200 cursor-pointer mb-0.5 truncate ${
              activeConversationId === conv.id
                ? "bg-sidebar-hover text-white font-medium"
                : "text-sidebar-text hover:bg-sidebar-hover hover:text-white"
            } ${collapsed ? "hidden" : ""}`}
            title={conv.title}
          >
            {conv.title}
          </button>
        ))}
      </div>

      {/* Admin nav */}
      {isAdmin && (
        <div className="px-2 py-2 border-t border-sidebar-border">
          <button
            onClick={() =>
              onViewChange?.(currentView === "admin" ? "chat" : "admin")
            }
            className={`w-full flex items-center gap-2 rounded-xl text-sm font-medium transition-all duration-200 cursor-pointer ${
              collapsed ? "justify-center p-2" : "px-3 py-2"
            } ${
              currentView === "admin"
                ? "bg-accent/20 text-accent"
                : "text-sidebar-text hover:bg-sidebar-hover hover:text-white"
            }`}
            title={collapsed ? adminLabel : undefined}
            aria-label={adminLabel}
          >
            <svg
              width={collapsed ? "18" : "14"}
              height={collapsed ? "18" : "14"}
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
            {!collapsed && adminLabel}
          </button>
        </div>
      )}

      {/* Usage dashboard */}
      {!collapsed && <UsageDashboard refreshKey={usageRefreshKey} />}

      {/* Collapse toggle */}
      <div className="p-2 border-t border-sidebar-border">
        <button
          onClick={onToggle}
          className="w-full flex items-center justify-center p-2 rounded-xl hover:bg-sidebar-hover text-sidebar-text-muted hover:text-white transition-colors duration-200 cursor-pointer"
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
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
            {collapsed ? (
              <path d="M9 18l6-6-6-6" />
            ) : (
              <path d="M15 18l-6-6 6-6" />
            )}
          </svg>
        </button>
      </div>
    </aside>
  );
}
