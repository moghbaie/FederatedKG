// Thin client for the registry API (/api) and the owner's own agent (/agent/<persona>/owner/*).

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string) {
    super(message);
  }
}

const TOKEN_KEY = "fkg.token";
let token: string | null = readToken();
let clockOffsetMs = 0;
let onUnauthorized: () => void = () => {};

function readToken(): string | null {
  try {
    return sessionStorage.getItem(TOKEN_KEY); // per tab: each tab can be a different persona
  } catch {
    return null;
  }
}

export function setToken(value: string | null): void {
  token = value;
  try {
    if (value) sessionStorage.setItem(TOKEN_KEY, value);
    else sessionStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage unavailable: keep the in-memory token only */
  }
}

export const hasToken = () => token !== null;
export const setUnauthorizedHandler = (fn: () => void) => (onUnauthorized = fn);

/** Current time on the registry clock (which may be advanced in test mode). */
export const registryNow = () => Date.now() + clockOffsetMs;

async function parse<T>(r: Response): Promise<T> {
  const now = r.headers.get("X-Registry-Now");
  if (now) clockOffsetMs = Date.parse(now) - Date.now();
  if (r.status === 401 && token) onUnauthorized();
  if (!r.ok) {
    const body = await r.json().catch(() => ({}));
    const detail = body?.detail ?? {};
    throw new ApiError(r.status, detail.code ?? `http_${r.status}`, detail.message ?? r.statusText);
  }
  return r.json() as Promise<T>;
}

function headers(json: boolean): HeadersInit {
  const h: Record<string, string> = {};
  if (token) h.Authorization = `Bearer ${token}`;
  if (json) h["Content-Type"] = "application/json";
  return h;
}

export async function api<T>(path: string, init: { method?: string; body?: unknown } = {}): Promise<T> {
  const r = await fetch(`/api${path}`, {
    method: init.method ?? "GET",
    headers: headers(init.body !== undefined),
    body: init.body !== undefined ? JSON.stringify(init.body) : undefined,
  });
  return parse<T>(r);
}

export async function ownGraph<T>(persona: string): Promise<T> {
  return parse<T>(await fetch(`/agent/${persona}/owner/graph`, { headers: headers(false) }));
}

export function newIdempotencyKey(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

/** Human-readable text for an API error code. */
export function describe(err: unknown): string {
  if (err instanceof ApiError) return `${err.code.replace(/_/g, " ")}${err.message && err.message !== err.code ? ` — ${err.message}` : ""}`;
  return String(err);
}
