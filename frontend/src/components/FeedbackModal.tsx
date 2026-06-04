import {useState, useCallback, useEffect} from "react";
import {authFetch} from "../api";

interface Props {
  open: boolean;
  rating: "up" | "down";
  conversationId: string | null;
  onClose: () => void;
  onSubmitted?: () => void;
}

const CATEGORIES_DOWN = [
  "Incorrect or incomplete",
  "Not what I asked for",
  "Slow or buggy",
  "Style or tone",
  "Safety or legal concern",
  "Other",
];

const CATEGORIES_UP = [
  "Accurate",
  "Helpful",
  "Well-written",
  "Easy to understand",
  "Other",
];

export default function FeedbackModal({
  open,
  rating,
  conversationId,
  onClose,
  onSubmitted,
}: Props) {
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [comment, setComment] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const reset = useCallback(() => {
    setSelected(new Set());
    setComment("");
    setSubmitting(false);
  }, []);

  const handleClose = useCallback(() => {
    reset();
    onClose();
  }, [reset, onClose]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") handleClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, handleClose]);

  const handleToggle = (cat: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(cat)) next.delete(cat);
      else next.add(cat);
      return next;
    });
  };

  const handleSubmit = async () => {
    setSubmitting(true);
    try {
      await authFetch("/api/v1/feedback", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          rating,
          categories: Array.from(selected),
          comment: comment.trim(),
          conversation_id: conversationId,
        }),
      });
      onSubmitted?.();
      handleClose();
    } catch {
      // network errors fail silently — feedback is best-effort
      setSubmitting(false);
    }
  };

  if (!open) return null;

  const categories = rating === "up" ? CATEGORIES_UP : CATEGORIES_DOWN;
  const canSubmit = selected.size > 0 || comment.trim().length > 0;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="feedback-title"
      className="fixed inset-0 z-50 flex items-center justify-center animate-fade-in-up"
    >
      {/* Backdrop — its own button so click-to-close is keyboard-accessible */}
      <button
        type="button"
        aria-label="Close feedback dialog"
        className="absolute inset-0 w-full h-full bg-black/50 backdrop-blur-sm cursor-default"
        onClick={handleClose}
      />

      {/* Panel — relative so it stacks above the absolutely-positioned backdrop */}
      <div className="relative w-full max-w-lg mx-4 rounded-2xl bg-surface-card border border-border-light shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-border-light">
          <h2
            id="feedback-title"
            className="text-base font-semibold text-text-primary"
          >
            Share feedback
          </h2>
          <button
            onClick={handleClose}
            className="p-1.5 rounded-lg text-text-tertiary hover:text-text-primary hover:bg-surface-hover transition-colors cursor-pointer"
            aria-label="Close"
          >
            <svg
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
            >
              <path d="M18 6L6 18M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Categories */}
        <div className="px-5 py-4">
          <div className="flex flex-wrap gap-2 mb-4">
            {categories.map((cat) => {
              const active = selected.has(cat);
              return (
                <button
                  key={cat}
                  onClick={() => handleToggle(cat)}
                  className={`px-3.5 py-1.5 rounded-full text-xs font-medium border transition-colors cursor-pointer ${
                    active
                      ? "bg-accent/10 border-accent text-accent"
                      : "bg-surface border-border-light text-text-secondary hover:border-border hover:text-text-primary"
                  }`}
                >
                  {cat}
                </button>
              );
            })}
          </div>

          <textarea
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            placeholder="Share details (optional)"
            rows={4}
            maxLength={2000}
            className="w-full px-3.5 py-2.5 rounded-xl border border-border-light bg-surface text-sm text-text-primary placeholder:text-text-tertiary resize-none focus:outline-none focus:border-border focus:ring-1 focus:ring-border/20 transition-colors"
          />
        </div>

        {/* Footer note + submit */}
        <div className="px-5 pb-4">
          <div className="text-xs text-text-tertiary bg-surface-hover rounded-lg px-3 py-2 mb-3">
            Your conversation will be included with your feedback to help
            improve the model.
          </div>
          <div className="flex justify-end">
            <button
              onClick={handleSubmit}
              disabled={!canSubmit || submitting}
              className="px-5 py-2 rounded-xl bg-accent text-white text-sm font-medium hover:bg-accent-hover disabled:opacity-40 disabled:cursor-not-allowed transition-colors cursor-pointer"
            >
              {submitting ? "Submitting…" : "Submit"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
