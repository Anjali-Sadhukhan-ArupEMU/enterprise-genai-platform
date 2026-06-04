import {useEffect, useState} from "react";
import {authFetch} from "../api";

interface ByModel {
  model: string;
  tokens: number;
  cost_inr: number;
  requests: number;
}

interface LastQuery {
  timestamp: string;
  model: string;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  cost_usd: number;
  cost_inr: number;
  latency_ms: number;
}

interface UsageSummary {
  currency: string;
  usd_to_inr: number;
  monthly_budget_inr: number;
  monthly: {
    spent_inr: number;
    remaining_inr: number;
    pct_used: number;
    tokens: number;
    requests: number;
  };
  today: {
    spent_inr: number;
    tokens: number;
    requests: number;
  };
  last_query: LastQuery | null;
  by_model: ByModel[];
}

interface Props {
  refreshKey: number;
}

const fmtInr = (n: number): string => {
  if (n === 0) return "₹0";
  if (n < 0.01) return "<₹0.01";
  if (n < 1) return `₹${n.toFixed(3)}`;
  return `₹${n.toFixed(2)}`;
};

const fmtNum = (n: number): string => n.toLocaleString();

// Frontend-only feature flag. Set VITE_USAGE_DASHBOARD_ENABLED=false to hide the
// sidebar Usage panel. Vite inlines VITE_* env vars at build time, loading them
// from .env.production (prod build) / .env (dev). Default = enabled.
const DASHBOARD_ENABLED =
  (import.meta.env.VITE_USAGE_DASHBOARD_ENABLED ?? "true").toLowerCase() !==
  "false";

export default function UsageDashboard({refreshKey}: Props) {
  const [data, setData] = useState<UsageSummary | null>(null);
  const [error, setError] = useState<boolean>(false);

  useEffect(() => {
    if (!DASHBOARD_ENABLED) return;
    let cancelled = false;
    authFetch("/api/v1/usage/summary")
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((d: UsageSummary) => {
        if (!cancelled) {
          setData(d);
          setError(false);
        }
      })
      .catch(() => !cancelled && setError(true));
    return () => {
      cancelled = true;
    };
  }, [refreshKey]);

  if (!DASHBOARD_ENABLED) return null;
  if (error || !data) return null;

  const pct = Math.min(100, data.monthly.pct_used);
  const barColor =
    pct < 50 ? "bg-emerald-500" : pct < 80 ? "bg-amber-500" : "bg-rose-500";
  const last = data.last_query;

  return (
    <div className="px-3 py-3 border-t border-sidebar-border space-y-2.5">
      <div className="flex items-center justify-between">
        <span className="text-[10px] font-semibold text-sidebar-text-muted uppercase tracking-wider">
          Usage
        </span>
        <span className="text-[10px] text-sidebar-text-muted">
          {data.monthly.requests} req{data.monthly.requests === 1 ? "" : "s"}
        </span>
      </div>

      {/* Monthly progress */}
      <div>
        <div className="flex justify-between text-[11px] text-sidebar-text mb-1">
          <span className="font-medium text-white">
            {fmtInr(data.monthly.spent_inr)}
          </span>
          <span className="text-sidebar-text-muted">
            / {fmtInr(data.monthly_budget_inr)} ({pct.toFixed(1)}%)
          </span>
        </div>
        <div className="h-1.5 bg-sidebar-hover rounded-full overflow-hidden">
          <div
            className={`h-full ${barColor} transition-all duration-500`}
            style={{width: `${pct}%`}}
          />
        </div>
      </div>

      {/* Today summary */}
      <div className="bg-sidebar-hover rounded-lg px-2.5 py-1.5">
        <div className="flex items-baseline justify-between">
          <span className="text-[10px] text-sidebar-text-muted uppercase tracking-wide">
            Today
          </span>
          <span className="text-[11px] text-white font-medium">
            {fmtInr(data.today.spent_inr)}
          </span>
        </div>
        <div className="text-[10px] text-sidebar-text-muted">
          {fmtNum(data.today.tokens)} tokens • {data.today.requests} requests
        </div>
      </div>

      {/* Last query */}
      {last && (
        <div className="bg-sidebar-hover rounded-lg px-2.5 py-1.5">
          <div className="flex items-baseline justify-between">
            <span className="text-[10px] text-sidebar-text-muted uppercase tracking-wide">
              Last query
            </span>
            <span className="text-[11px] text-white font-medium">
              {fmtInr(last.cost_inr)}
            </span>
          </div>
          <div className="text-[10px] text-sidebar-text-muted">
            {last.prompt_tokens}↑ {last.completion_tokens}↓ tokens •{" "}
            {Math.round(last.latency_ms)}ms
          </div>
          <div
            className="text-[10px] text-sidebar-text-muted truncate"
            title={last.model}
          >
            {last.model}
          </div>
        </div>
      )}
    </div>
  );
}
