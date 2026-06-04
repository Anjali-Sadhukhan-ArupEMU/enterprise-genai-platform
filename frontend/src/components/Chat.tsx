import {useCallback, useEffect, useRef, useState} from "react";
import {createPortal} from "react-dom";
import toast from "react-hot-toast";
import {LogoIcon} from "./Logo";
import MarkdownMessage from "./MarkdownMessage";
import FeedbackModal from "./FeedbackModal";
import {authFetch} from "../api";

interface Citation {
  title: string;
  url: string;
  snippet?: string;
}

interface Message {
  role: "user" | "assistant";
  content: string;
  timestamp?: Date;
  citations?: Citation[];
  webSearching?: boolean;
}

interface Props {
  mode: "quick" | "deep" | "code" | "creative";
  conversationId: string | null;
  onConversationId: (id: string) => void;
  onTitle: (id: string, title: string) => void;
}

const SUGGESTIONS = [
  "Write a Python script to parse structural analysis output and flag overstressed members",
  "Explain the difference between SLS and ULS load combinations to Eurocode",
  "Help me automate a Grasshopper/Rhino workflow for parametric facade design",
  "Summarise embodied carbon reduction strategies for a steel-framed building",
];

export default function Chat({
  mode,
  conversationId,
  onConversationId,
  onTitle,
}: Props) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [hasContentBelow, setHasContentBelow] = useState(false);
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const lastUserMessageRef = useRef<HTMLDivElement>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const userMessageCountRef = useRef(0);

  // Recompute whether there is any content below the visible viewport.
  // Threshold of 24px filters out 1-2 pixels of sub-pixel scroll noise.
  const recomputeContentBelow = useCallback(() => {
    const el = scrollContainerRef.current;
    if (!el) {
      setHasContentBelow(false);
      return;
    }
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    setHasContentBelow(distanceFromBottom > 24);
  }, []);

  // Listen for manual scrolls inside the messages container.
  useEffect(() => {
    const el = scrollContainerRef.current;
    if (!el) return;
    el.addEventListener("scroll", recomputeContentBelow, {passive: true});
    recomputeContentBelow();
    return () => el.removeEventListener("scroll", recomputeContentBelow);
  }, [recomputeContentBelow, messages.length === 0]);

  // Recompute after every message/token update — streaming grows scrollHeight
  // even when the user doesn't scroll, so we have to poll the layout.
  useEffect(() => {
    recomputeContentBelow();
  }, [messages, loading, recomputeContentBelow]);

  // When the user sends a new message, anchor that message at the top of
  // the viewport (ChatGPT-style). The assistant response then streams in
  // below. We never auto-follow during streaming — the viewport stays
  // where the user left it; the pill announces off-screen content.
  useEffect(() => {
    const userCount = messages.filter((m) => m.role === "user").length;
    if (userCount > userMessageCountRef.current) {
      userMessageCountRef.current = userCount;
      requestAnimationFrame(() => {
        lastUserMessageRef.current?.scrollIntoView({
          behavior: "smooth",
          block: "start",
        });
        recomputeContentBelow();
      });
    }
  }, [messages, recomputeContentBelow]);

  const jumpToLatest = useCallback(() => {
    endRef.current?.scrollIntoView({behavior: "smooth", block: "end"});
  }, []);

  // Auto-resize textarea
  useEffect(() => {
    const el = textareaRef.current;
    if (el) {
      el.style.height = "auto";
      el.style.height = Math.min(el.scrollHeight, 160) + "px";
    }
  }, [input]);

  const sendMessage = useCallback(
    async (text?: string) => {
      const msg = (text ?? input).trim();
      if (!msg || loading) return;

      setInput("");
      setMessages((prev) => [
        ...prev,
        {role: "user", content: msg, timestamp: new Date()},
      ]);
      setLoading(true);

      try {
        const res = await authFetch("/api/v1/chat?stream=true", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({
            message: msg,
            mode,
            stream: true,
            conversation_id: conversationId,
            // Web search is gated automatically by the backend based on the
            // query / model response — no user-facing toggle.
          }),
        });

        if (!res.ok) throw new Error(`HTTP ${res.status}`);

        const reader = res.body?.getReader();
        const decoder = new TextDecoder();
        let assistantContent = "";
        let citations: Citation[] = [];
        let webSearching = false;

        setMessages((prev) => [
          ...prev,
          {role: "assistant", content: "", timestamp: new Date()},
        ]);

        if (reader) {
          // `assistantContent` is the full text received so far (the target).
          // `displayedLen` is how much of it is currently shown. A steady
          // drain advances the displayed text at a smooth pace so that bursty
          // / stalling model delivery still renders continuously instead of
          // jumping in chunks.
          let displayedLen = 0;
          let streamFinished = false;

          const render = () => {
            setMessages((prev) => {
              const updated = [...prev];
              updated[updated.length - 1] = {
                role: "assistant",
                content: assistantContent.slice(0, displayedLen),
                citations,
                webSearching,
                timestamp: new Date(),
              };
              return updated;
            });
          };

          // Typewriter drain: advance the displayed text toward the buffer a
          // few characters per tick. While streaming, keep a small backlog so
          // we never run dry between bursts; once the stream is finished,
          // flush everything quickly.
          const drainStep = () => {
            const remaining = assistantContent.length - displayedLen;
            if (remaining > 0) {
              // Reveal faster when the backlog grows so we don't lag behind a
              // fast burst, but keep it smooth for steady streams.
              const step = streamFinished
                ? remaining
                : Math.max(2, Math.ceil(remaining / 8));
              displayedLen += step;
              render();
            }
          };
          const drainTimer = setInterval(drainStep, 24);

          try {
            let sseBuffer = "";
            let streamDone = false;
            while (!streamDone) {
              const {done, value} = await reader.read();
              if (done) break;
              sseBuffer += decoder.decode(value, {stream: true});
              // Process complete SSE lines only; keep partial line in buffer.
              let nlIndex = sseBuffer.indexOf("\n");
              while (nlIndex !== -1) {
                const line = sseBuffer.slice(0, nlIndex);
                sseBuffer = sseBuffer.slice(nlIndex + 1);
                nlIndex = sseBuffer.indexOf("\n");
                if (!line.startsWith("data: ")) continue;
                const payload = line.slice(6).trim();
                if (payload === "[DONE]") {
                  streamDone = true;
                  break;
                }
                try {
                  const parsed = JSON.parse(payload);
                  if (parsed.error) {
                    assistantContent += `\n[Error: ${parsed.error}]`;
                  } else if (parsed.content) {
                    assistantContent += parsed.content;
                  }
                  if (parsed.status === "web_search") {
                    webSearching = true;
                    render();
                  }
                  if (Array.isArray(parsed.citations)) {
                    citations = parsed.citations as Citation[];
                    webSearching = false;
                    render();
                  }
                  if (parsed.conversation_id) {
                    onConversationId(parsed.conversation_id);
                    onTitle(parsed.conversation_id, msg.slice(0, 60));
                  }
                } catch {
                  // skip malformed SSE lines
                }
              }
            }
          } finally {
            // Stop draining and force the full text to render immediately.
            streamFinished = true;
            clearInterval(drainTimer);
            displayedLen = assistantContent.length;
            render();
          }
        }
      } catch (err: any) {
        setMessages((prev) => [
          ...prev,
          {
            role: "assistant",
            content: `Error: ${err.message}`,
            timestamp: new Date(),
          },
        ]);
      } finally {
        setLoading(false);
      }
    },
    [
      input,
      mode,
      conversationId,
      loading,
      onConversationId,
      onTitle,
    ],
  );

  const handleKey = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  // ── Empty state ──────────────────────────────────────────────────────
  if (messages.length === 0) {
    return (
      <div className="flex flex-col flex-1 items-center justify-center px-6">
        <div className="max-w-2xl w-full text-center mb-12">
          <h1 className="text-3xl font-semibold text-text-primary tracking-tight mb-3">
            What can I help you with?
          </h1>
          <p className="text-base text-text-tertiary leading-relaxed">
            Ask me anything — I can help with engineering analysis, computation,
            coding, and writing.
          </p>
        </div>

        {/* Suggestion chips */}
        <div className="max-w-2xl w-full grid grid-cols-1 sm:grid-cols-2 gap-2.5 mb-10">
          {SUGGESTIONS.map((s) => (
            <button
              key={s}
              onClick={() => sendMessage(s)}
              className="text-left px-4 py-3.5 rounded-2xl border border-border-light bg-surface-card hover:bg-surface-hover text-sm text-text-secondary hover:text-text-primary transition-all duration-200 cursor-pointer"
            >
              {s}
            </button>
          ))}
        </div>

        {/* Input */}
        <div className="max-w-2xl w-full">
          <PromptComposer
            input={input}
            loading={loading}
            textareaRef={textareaRef}
            onChange={setInput}
            onSend={() => sendMessage()}
            onKeyDown={handleKey}
          />
        </div>
      </div>
    );
  }

  // ── Conversation view ────────────────────────────────────────────────
  // Compute index of the most recent user message so we can attach a ref
  // and scroll it to the top of the viewport when a new turn starts.
  let lastUserIdx = -1;
  for (let i = messages.length - 1; i >= 0; i--) {
    if (messages[i].role === "user") {
      lastUserIdx = i;
      break;
    }
  }

  return (
    <div className="flex flex-col flex-1 overflow-hidden">
      {/* Messages */}
      <div
        ref={scrollContainerRef}
        className="flex-1 overflow-y-auto px-6 py-6 relative"
      >
        <div className="max-w-2xl mx-auto flex flex-col gap-5">
          {messages.map((msg, i) => (
            <div
              key={i}
              ref={i === lastUserIdx ? lastUserMessageRef : undefined}
              className="animate-fade-in-up scroll-mt-6"
            >
              {msg.role === "user" ? (
                <UserMessage content={msg.content} />
              ) : (
                <AssistantMessage
                  content={msg.content}
                  isStreaming={loading && i === messages.length - 1}
                  conversationId={conversationId}
                  citations={msg.citations}
                  webSearching={msg.webSearching}
                />
              )}
            </div>
          ))}

          {loading && messages[messages.length - 1]?.role !== "assistant" && (
            <div className="animate-fade-in-up">
              <ThinkingIndicator />
            </div>
          )}

          <div ref={endRef} />
        </div>

        {/* Jump-to-latest pill (ChatGPT-style). Visible while streaming
            only when there is actually content below the visible area. */}
        {loading && hasContentBelow && (
          <button
            onClick={jumpToLatest}
            className="sticky bottom-4 left-1/2 -translate-x-1/2 flex items-center gap-2 px-3.5 py-2 rounded-full bg-surface-card border border-border-light shadow-md text-xs text-text-secondary hover:text-text-primary hover:bg-surface-hover transition-all cursor-pointer"
            aria-label="Jump to latest"
          >
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-accent opacity-60"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-accent"></span>
            </span>
            Writing below
            <svg
              width="12"
              height="12"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <polyline points="6 9 12 15 18 9" />
            </svg>
          </button>
        )}
      </div>

      {/* Sticky input */}
      <div className="border-t border-border-light bg-surface-card px-6 py-4">
        <div className="max-w-2xl mx-auto">
          <PromptComposer
            input={input}
            loading={loading}
            textareaRef={textareaRef}
            onChange={setInput}
            onSend={() => sendMessage()}
            onKeyDown={handleKey}
          />
        </div>
      </div>
    </div>
  );
}

/* ── Sub-components ─────────────────────────────────────────────────── */

function UserMessage({content}: {content: string}) {
  return (
    <div className="group flex flex-col items-end gap-1">
      <div className="max-w-[80%] px-5 py-3.5 rounded-2xl bg-user-bubble text-white text-sm leading-relaxed">
        <div className="whitespace-pre-wrap">{content}</div>
      </div>
      <div className="opacity-0 group-hover:opacity-100 transition-opacity duration-150">
        <MessageCopyButton text={content} />
      </div>
    </div>
  );
}

function WebSearchingIndicator() {
  return (
    <div className="flex items-center gap-2 text-text-tertiary text-sm">
      <svg
        className="animate-spin"
        width="14"
        height="14"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <line x1="12" y1="2" x2="12" y2="6" />
        <line x1="12" y1="18" x2="12" y2="22" />
        <line x1="4.93" y1="4.93" x2="7.76" y2="7.76" />
        <line x1="16.24" y1="16.24" x2="19.07" y2="19.07" />
        <line x1="2" y1="12" x2="6" y2="12" />
        <line x1="18" y1="12" x2="22" y2="12" />
        <line x1="4.93" y1="19.07" x2="7.76" y2="16.24" />
        <line x1="16.24" y1="7.76" x2="19.07" y2="4.93" />
      </svg>
      Searching the web…
    </div>
  );
}

function SourcesFooter({citations}: {citations: Citation[]}) {
  return (
    <div className="mt-2 flex flex-col gap-1.5">
      <div className="flex items-center gap-1.5 text-xs font-medium text-text-tertiary">
        <svg
          width="12"
          height="12"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <circle cx="12" cy="12" r="10" />
          <line x1="2" y1="12" x2="22" y2="12" />
          <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
        </svg>
        Sources
      </div>
      <div className="flex flex-wrap gap-1.5">
        {citations.map((c, i) => {
          let host = c.url;
          try {
            host = new URL(c.url).hostname.replace(/^www\./, "");
          } catch {
            // leave host as the raw url if parsing fails
          }
          return (
            <a
              key={`${c.url}-${i}`}
              href={c.url}
              target="_blank"
              rel="noopener noreferrer"
              title={c.snippet || c.title || c.url}
              className="group/src inline-flex items-center gap-1.5 max-w-65 px-2.5 py-1.5 rounded-lg border border-border-light bg-surface-card hover:bg-surface-hover transition-colors duration-150"
            >
              <span className="shrink-0 w-4 h-4 rounded-full bg-accent/10 text-accent text-[10px] font-semibold flex items-center justify-center">
                {i + 1}
              </span>
              <span className="truncate text-xs text-text-secondary group-hover/src:text-text-primary">
                {c.title || host}
              </span>
              <span className="shrink-0 text-[10px] text-text-tertiary">
                {host}
              </span>
            </a>
          );
        })}
      </div>
    </div>
  );
}

function AssistantMessage({
  content,
  isStreaming,
  conversationId,
  citations,
  webSearching,
}: {
  content: string;
  isStreaming: boolean;
  conversationId: string | null;
  citations?: Citation[];
  webSearching?: boolean;
}) {
  const [modal, setModal] = useState<null | "up" | "down">(null);
  const [submittedRating, setSubmittedRating] = useState<null | "up" | "down">(
    null,
  );
  const [fullScreen, setFullScreen] = useState(false);

  const handleQuickUp = async () => {
    if (submittedRating === "up") {
      // toggle off — visual only, original feedback stays in logs
      setSubmittedRating(null);
      toast("Feedback removed");
      return;
    }
    setSubmittedRating("up");
    try {
      await authFetch("/api/v1/feedback", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          rating: "up",
          categories: [],
          comment: "",
          conversation_id: conversationId,
        }),
      });
      toast.success("Thanks for the feedback");
    } catch {
      // best-effort
    }
  };

  const handleDownClick = () => {
    if (submittedRating === "down") {
      // toggle off — visual only, no modal
      setSubmittedRating(null);
      toast("Feedback removed");
      return;
    }
    setModal("down");
  };

  return (
    <div className="group flex gap-3">
      <div className="flex-shrink-0 mt-0.5">
        <LogoIcon className="w-7 h-7" />
      </div>
      <div className="flex-1 min-w-0">
        <div className="relative px-5 py-4 rounded-2xl bg-ai-bubble border border-border-light text-sm text-text-primary leading-relaxed">
          {!isStreaming && content && (
            <button
              onClick={() => setFullScreen(true)}
              title="Open in full screen"
              aria-label="Open in full screen"
              className="absolute top-2 right-2 p-1.5 rounded-md text-text-tertiary hover:text-text-primary hover:bg-surface-hover opacity-0 group-hover:opacity-100 transition-opacity duration-150 cursor-pointer"
            >
              <svg
                width="14"
                height="14"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <polyline points="15 3 21 3 21 9" />
                <polyline points="9 21 3 21 3 15" />
                <line x1="21" y1="3" x2="14" y2="10" />
                <line x1="3" y1="21" x2="10" y2="14" />
              </svg>
            </button>
          )}
          {content && (
            <div className={isStreaming ? "typing-cursor" : ""}>
              {isStreaming ? (
                <div className="whitespace-pre-wrap">{content}</div>
              ) : (
                <MarkdownMessage content={content} />
              )}
            </div>
          )}
          {!content && webSearching && <WebSearchingIndicator />}
          {!content && !webSearching && (
            <div className={isStreaming ? "typing-cursor" : ""}> </div>
          )}
        </div>
        {citations && citations.length > 0 && (
          <SourcesFooter citations={citations} />
        )}
        {!isStreaming && content && (
          <div className="mt-1 flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity duration-150">
            <MessageCopyButton text={content} />
            <ActionIconButton
              label="Good response"
              active={submittedRating === "up"}
              onClick={handleQuickUp}
              icon="thumbs-up"
            />
            <ActionIconButton
              label="Bad response"
              active={submittedRating === "down"}
              onClick={handleDownClick}
              icon="thumbs-down"
            />
            <ActionIconButton
              label="Open in full screen"
              active={false}
              onClick={() => setFullScreen(true)}
              icon="expand"
            />
          </div>
        )}
        <FeedbackModal
          open={modal !== null}
          rating={modal ?? "down"}
          conversationId={conversationId}
          onClose={() => setModal(null)}
          onSubmitted={() => {
            setSubmittedRating(modal);
            toast.success("Thanks for the feedback");
          }}
        />
        <FullScreenReader
          open={fullScreen}
          content={content}
          onClose={() => setFullScreen(false)}
        />
      </div>
    </div>
  );
}

function ActionIconButton({
  label,
  active,
  onClick,
  icon,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
  icon: "thumbs-up" | "thumbs-down" | "expand";
}) {
  return (
    <button
      onClick={onClick}
      title={label}
      aria-label={label}
      className={`p-1.5 rounded-md transition-colors cursor-pointer ${
        active
          ? "text-accent bg-accent/10"
          : "text-text-tertiary hover:text-text-secondary hover:bg-surface-hover"
      }`}
    >
      {icon === "thumbs-up" && (
        <svg
          width="14"
          height="14"
          viewBox="0 0 24 24"
          fill={active ? "currentColor" : "none"}
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M7 10v12" />
          <path d="M15 5.88L14 10h5.83a2 2 0 011.92 2.56l-2.33 8A2 2 0 0117.5 22H7V10l4-9a2 2 0 012 1.69V6" />
        </svg>
      )}
      {icon === "thumbs-down" && (
        <svg
          width="14"
          height="14"
          viewBox="0 0 24 24"
          fill={active ? "currentColor" : "none"}
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M17 14V2" />
          <path d="M9 18.12L10 14H4.17a2 2 0 01-1.92-2.56l2.33-8A2 2 0 016.5 2H17v12l-4 9a2 2 0 01-2-1.69V18" />
        </svg>
      )}
      {icon === "expand" && (
        <svg
          width="14"
          height="14"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <polyline points="15 3 21 3 21 9" />
          <polyline points="9 21 3 21 3 15" />
          <line x1="21" y1="3" x2="14" y2="10" />
          <line x1="3" y1="21" x2="10" y2="14" />
        </svg>
      )}
    </button>
  );
}

function MessageCopyButton({text}: {text: string}) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // clipboard may be unavailable outside secure contexts
    }
  };

  return (
    <button
      onClick={handleCopy}
      className="flex items-center gap-1 px-2 py-1 rounded-md text-[11px] text-text-tertiary hover:text-text-secondary hover:bg-surface-hover transition-colors cursor-pointer"
      aria-label={copied ? "Copied" : "Copy message"}
      title={copied ? "Copied" : "Copy message"}
    >
      {copied ? (
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
      ) : (
        <svg
          width="12"
          height="12"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
          <path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1" />
        </svg>
      )}
      <span>{copied ? "Copied" : "Copy"}</span>
    </button>
  );
}

function FullScreenReader({
  open,
  content,
  onClose,
}: {
  open: boolean;
  content: string;
  onClose: () => void;
}) {
  // Lock body scroll + close on Esc while the reader is open.
  useEffect(() => {
    if (!open) return;
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = prevOverflow;
      window.removeEventListener("keydown", onKey);
    };
  }, [open, onClose]);

  if (!open) return null;

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(content);
      toast.success("Copied to clipboard");
    } catch {
      // clipboard may be unavailable outside secure contexts
    }
  };

  // Render through a portal so the modal escapes any ancestor that creates
  // a containing block for position:fixed (e.g. transforms from animations).
  return createPortal(
    <div
      className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex flex-col animate-fade-in-up"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label="Full screen response"
    >
      <div
        className="flex-1 flex flex-col bg-surface-card overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-3 border-b border-border-light bg-surface-card">
          <div className="flex items-center gap-2 text-sm text-text-secondary">
            <LogoIcon className="w-5 h-5" />
            <span>Full-screen reader</span>
          </div>
          <div className="flex items-center gap-1">
            <button
              onClick={handleCopy}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs text-text-secondary hover:text-text-primary hover:bg-surface-hover transition-colors cursor-pointer"
              aria-label="Copy response"
              title="Copy"
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
                <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
                <path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1" />
              </svg>
              Copy
            </button>
            <button
              onClick={onClose}
              className="p-1.5 rounded-md text-text-tertiary hover:text-text-primary hover:bg-surface-hover transition-colors cursor-pointer"
              aria-label="Close (Esc)"
              title="Close (Esc)"
            >
              <svg
                width="18"
                height="18"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <line x1="18" y1="6" x2="6" y2="18" />
                <line x1="6" y1="6" x2="18" y2="18" />
              </svg>
            </button>
          </div>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-8 md:px-16 lg:px-24 py-10">
          <div className="w-full text-[15px] leading-7 text-text-primary">
            <MarkdownMessage content={content} />
          </div>
          <div className="w-full flex justify-center mt-12 pt-8 border-t border-border-light">
            <button
              onClick={onClose}
              className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm text-text-secondary hover:text-text-primary hover:bg-surface-hover border border-border-light transition-colors cursor-pointer"
              aria-label="Close (Esc)"
            >
              <svg
                width="14"
                height="14"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <line x1="18" y1="6" x2="6" y2="18" />
                <line x1="6" y1="6" x2="18" y2="18" />
              </svg>
              Close
              <span className="ml-1 text-[10px] text-text-tertiary border border-border-light rounded px-1.5 py-0.5">
                Esc
              </span>
            </button>
          </div>
        </div>
      </div>
    </div>,
    document.body,
  );
}

function ThinkingIndicator() {
  return (
    <div className="flex gap-3">
      <div className="flex-shrink-0 mt-0.5">
        <LogoIcon className="w-7 h-7" />
      </div>
      <div className="px-5 py-4 rounded-2xl bg-ai-bubble border border-border-light">
        <div className="flex gap-1.5">
          <span className="w-1.5 h-1.5 bg-text-tertiary rounded-full animate-bounce [animation-delay:0ms]" />
          <span className="w-1.5 h-1.5 bg-text-tertiary rounded-full animate-bounce [animation-delay:150ms]" />
          <span className="w-1.5 h-1.5 bg-text-tertiary rounded-full animate-bounce [animation-delay:300ms]" />
        </div>
      </div>
    </div>
  );
}

function PromptComposer({
  input,
  loading,
  textareaRef,
  onChange,
  onSend,
  onKeyDown,
}: {
  input: string;
  loading: boolean;
  textareaRef: React.RefObject<HTMLTextAreaElement | null>;
  onChange: (v: string) => void;
  onSend: () => void;
  onKeyDown: (e: React.KeyboardEvent) => void;
}) {
  return (
    <div className="relative flex items-end gap-2 rounded-2xl border border-border-light bg-surface-card shadow-sm focus-within:border-border focus-within:ring-1 focus-within:ring-border/20 transition-all duration-200">
      <textarea
        ref={textareaRef as React.RefObject<HTMLTextAreaElement>}
        value={input}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={onKeyDown}
        placeholder="Ask anything…"
        className="flex-1 pl-4 py-3.5 bg-transparent text-sm text-text-primary placeholder:text-text-tertiary resize-none focus:outline-none leading-relaxed max-h-40"
        rows={1}
      />

      {/* Voice – hidden until dictation is implemented */}
      {/* <button className="flex-shrink-0 p-3 text-text-tertiary hover:text-text-secondary transition-colors duration-200 cursor-pointer">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
          <path d="M12 1a3 3 0 00-3 3v8a3 3 0 006 0V4a3 3 0 00-3-3z" />
          <path d="M19 10v2a7 7 0 01-14 0v-2" />
          <line x1="12" y1="19" x2="12" y2="23" />
          <line x1="8" y1="23" x2="16" y2="23" />
        </svg>
      </button> */}

      {/* Send */}
      <button
        onClick={onSend}
        disabled={loading || !input.trim()}
        className="flex-shrink-0 m-1.5 h-9 w-9 inline-flex items-center justify-center rounded-xl bg-accent text-white hover:bg-accent-hover disabled:opacity-30 disabled:cursor-not-allowed transition-all duration-200 cursor-pointer"
      >
        <svg
          width="16"
          height="16"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <line x1="22" y1="2" x2="11" y2="13" />
          <polygon points="22 2 15 22 11 13 2 9 22 2" />
        </svg>
      </button>
    </div>
  );
}
