import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { registryNow } from "./api";

export const BANNER = "Simulated researchers and synthetic knowledge graphs. No real researcher participation.";

export const label = (s: string) => s.replace(/_/g, " ");

const STATUS_TONE: Record<string, string> = {
  ACTIVE: "ok", APPROVED: "ok", COMPLETED: "ok", allow: "ok",
  PENDING: "warn", RUNNING: "warn", PAUSED: "warn", DRAFT: "neutral",
  REJECTED: "bad", CANCELLED: "bad", EXPIRED: "bad", FAILED: "bad", CLOSED: "neutral", deny: "bad",
};

export function Pill({ value, tone, testId }: { value: string; tone?: string; testId?: string }) {
  return (
    <span className={`pill ${tone ?? STATUS_TONE[value] ?? "neutral"}`} data-testid={testId}>
      {label(value)}
    </span>
  );
}

const BAND_TONE: Record<string, string> = { high: "ok", medium: "info", low: "warn", insufficient_disclosure: "neutral" };

export function Band({ value, testId }: { value: string; testId?: string }) {
  return <Pill value={value} tone={BAND_TONE[value] ?? "neutral"} testId={testId} />;
}

export function Meter({ value, testId }: { value: number; testId?: string }) {
  const pct = Math.round(value * 100);
  return (
    <span className="meter" data-testid={testId} title={`${pct}% of published topics overlap`}>
      <span className="meter-track"><span className="meter-fill" style={{ width: `${pct}%` }} /></span>
      <span className="meter-value">{value.toFixed(2)}</span>
    </span>
  );
}

function formatRemaining(ms: number): string {
  if (ms <= 0) return "expired";
  const s = Math.floor(ms / 1000);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  return `${h}h ${String(m).padStart(2, "0")}m ${String(s % 60).padStart(2, "0")}s`;
}

/** Countdown on the registry clock, so test-clock advances are reflected. */
export function Countdown({ until }: { until: string | null }) {
  const [now, setNow] = useState(registryNow());
  useEffect(() => {
    const t = setInterval(() => setNow(registryNow()), 1000);
    return () => clearInterval(t);
  }, []);
  if (!until) return <span className="muted">not started</span>;
  return <span className="mono" data-testid="countdown">{formatRemaining(Date.parse(until) - now)}</span>;
}

export function TopicChips({ topics, highlight = [] }: { topics: string[]; highlight?: string[] }) {
  return (
    <span className="chips">
      {topics.map((t) => (
        <span key={t} className={`chip ${highlight.includes(t) ? "chip-match" : ""}`}>{label(t)}</span>
      ))}
    </span>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="empty">{children}</p>;
}

export function ErrorBox({ error }: { error: unknown }) {
  if (!error) return null;
  return <p className="error" role="alert">{error instanceof Error ? error.message : String(error)}</p>;
}

export function PageHeader({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <header className="page-header">
      <h1>{title}</h1>
      {children && <p className="muted">{children}</p>}
    </header>
  );
}

// ---- toasts --------------------------------------------------------------------------------------

type Toast = { id: number; text: string; tone: "ok" | "bad" };
const ToastContext = createContext<(text: string, tone?: "ok" | "bad") => void>(() => {});

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const push = useCallback((text: string, tone: "ok" | "bad" = "ok") => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t, { id, text, tone }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 4500);
  }, []);
  return (
    <ToastContext.Provider value={push}>
      {children}
      <div className="toasts" role="status" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className={`toast ${t.tone}`} data-testid="toast">{t.text}</div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export const useToast = () => useContext(ToastContext);
