import {useEffect, useState} from "react";
import {Toaster} from "react-hot-toast";
import Chat from "./components/Chat";
import Header from "./components/Header";
import Sidebar from "./components/Sidebar";
import LoginPage from "./components/LoginPage";
import AdminPanel from "./components/AdminPanel";
import {AuthProvider, useAuth} from "./auth/AuthProvider";
import {authFetch} from "./api";

type ChatMode = "quick" | "deep" | "code" | "creative";

interface ConversationItem {
  id: string;
  title: string;
}

export interface AvailableModel {
  model_id: string;
  display_name: string;
}

const AUTO_MODEL_ID = "auto";

const FALLBACK_MODELS: AvailableModel[] = [
  {model_id: "gpt-4.1-nano", display_name: "GPT-4.1 Nano"},
  {model_id: "gpt-4o-mini", display_name: "GPT-4o Mini (test)"},
  {model_id: "gpt-4.1-mini", display_name: "GPT-4.1 Mini"},
];

function AppContent() {
  const {user, isLoading, logout} = useAuth();
  const [mode, setMode] = useState<ChatMode>("quick");
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [conversations, setConversations] = useState<ConversationItem[]>([]);
  const [key, setKey] = useState(0);
  const [view, setView] = useState<"chat" | "admin">("chat");
  const [models, setModels] = useState<AvailableModel[]>(FALLBACK_MODELS);
  const [selectedModel, setSelectedModel] = useState<string>(
    FALLBACK_MODELS[0].model_id,
  );

  // Fetch available models once logged in (overrides fallback if backend is up)
  useEffect(() => {
    if (!user) return;
    authFetch("/api/v1/models")
      .then((r) => {
        if (!r.ok) throw new Error("Failed to load models");
        return r.json();
      })
      .then((data: AvailableModel[]) => {
        setModels(data);
        setSelectedModel((prev) => {
          if (data.length === 0) {
            return AUTO_MODEL_ID;
          }

          const ids = data.map((m) => m.model_id);
          return ids.includes(prev) ? prev : data[0].model_id;
        });
      })
      .catch(() => {});
  }, [user]);

  // While auth is resolving (e.g. processing a login redirect), show a
  // neutral loading screen so the login page doesn't flash before the
  // authenticated app appears.
  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-surface">
        <div className="h-8 w-8 rounded-full border-2 border-border border-t-accent animate-spin" />
      </div>
    );
  }

  // If not logged in, show login page
  if (!user) return <LoginPage />;

  const handleNewConversation = () => {
    setConversationId(null);
    setKey((k) => k + 1);
    setView("chat");
  };

  const handleConversationId = (id: string) => {
    setConversationId(id);
    setConversations((prev) => {
      if (prev.some((c) => c.id === id)) return prev;
      return [{id, title: "New conversation"}, ...prev];
    });
  };

  const handleConversationTitle = (id: string, title: string) => {
    setConversations((prev) =>
      prev.map((c) => (c.id === id ? {...c, title} : c)),
    );
  };

  const handleSelectConversation = (id: string) => {
    setConversationId(id);
    setKey((k) => k + 1);
    setView("chat");
  };

  return (
    <div className="flex h-screen bg-surface font-sans antialiased">
      <Sidebar
        mode={mode}
        onModeChange={setMode}
        collapsed={sidebarCollapsed}
        onToggle={() => setSidebarCollapsed(!sidebarCollapsed)}
        conversations={conversations}
        activeConversationId={conversationId}
        onSelectConversation={handleSelectConversation}
        onNewConversation={handleNewConversation}
        isAdmin={user.isAdmin}
        currentView={view}
        onViewChange={setView}
      />

      <div className="flex flex-col flex-1 min-w-0">
        <Header
          onNewConversation={handleNewConversation}
          userName={user.name}
          isAdmin={user.isAdmin}
          onLogout={logout}
          models={models}
          selectedModel={selectedModel}
          onModelChange={setSelectedModel}
        />

        <main className="flex-1 flex flex-col overflow-hidden bg-surface">
          {view === "admin" && user.isAdmin ? (
            <AdminPanel />
          ) : (
            <Chat
              key={key}
              mode={mode}
              conversationId={conversationId}
              onConversationId={handleConversationId}
              onTitle={handleConversationTitle}
            />
          )}
        </main>
      </div>
    </div>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <AppContent />
      <Toaster
        position="top-right"
        toastOptions={{
          duration: 4000,
          style: {
            fontSize: "13px",
            borderRadius: "10px",
            padding: "10px 16px",
          },
          success: {
            style: {background: "#f0fdf4", color: "#166534", border: "none"},
          },
          error: {
            style: {background: "#fef2f2", color: "#991b1b", border: "none"},
            duration: 5000,
          },
        }}
      />
    </AuthProvider>
  );
}
