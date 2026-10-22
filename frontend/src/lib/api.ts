"use client";

import type { ModelInfo, Mode, Source } from "./types";

/** All calls go to this origin; the Next.js route handler proxies to FastAPI. */
const CSRF = { "X-Strata-CSRF": "1" };

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

let refreshing: Promise<boolean> | null = null;

function refreshSession(): Promise<boolean> {
  refreshing ??= fetch("/api/auth/refresh", { method: "POST", headers: CSRF })
    .then((r) => r.ok)
    .catch(() => false)
    .finally(() => setTimeout(() => (refreshing = null), 0));
  return refreshing;
}

function toLogin() {
  if (typeof window !== "undefined" && window.location.pathname !== "/login") {
    const next = encodeURIComponent(window.location.pathname);
    window.location.href = `/login?next=${next}`;
  }
}

async function errorMessage(res: Response): Promise<string> {
  try {
    const body = await res.json();
    if (typeof body.detail === "string") return body.detail;
    if (Array.isArray(body.detail))
      return body.detail.map((d: { msg?: string }) => d.msg?.replace(/^Value error, /, "") ?? "Invalid input").join("; ");
  } catch {
    /* not JSON */
  }
  return res.status === 502 ? "The server is unreachable." : res.statusText || "Request failed";
}

/** fetch() with CSRF header, JSON defaults and a single transparent token refresh. */
export async function request(path: string, init: RequestInit = {}, retry = true): Promise<Response> {
  const isForm = init.body instanceof FormData;
  const res = await fetch(path, {
    ...init,
    credentials: "same-origin",
    headers: {
      ...CSRF,
      ...(init.body && !isForm ? { "Content-Type": "application/json" } : {}),
      ...init.headers,
    },
  });
  if (res.status === 401 && retry && !path.startsWith("/api/auth/login")) {
    if (await refreshSession()) return request(path, init, false);
    toLogin();
  }
  return res;
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await request(path, init);
  if (!res.ok) throw new ApiError(res.status, await errorMessage(res));
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const fetcher = <T,>(path: string) => api<T>(path);

export const post = <T,>(path: string, body?: unknown) =>
  api<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });
export const patch = <T,>(path: string, body: unknown) =>
  api<T>(path, { method: "PATCH", body: JSON.stringify(body) });
export const del = (path: string) => api<void>(path, { method: "DELETE" });

/** Open an authenticated file in a new tab (cookie auth rides along). */
export async function openFile(fileId: number) {
  await api("/api/auth/me"); // refresh the session first if it lapsed
  window.open(`/api/files/${fileId}/download`, "_blank", "noopener");
}

export async function downloadUrl(path: string) {
  await api("/api/auth/me");
  const a = document.createElement("a");
  a.href = path;
  a.click();
}

// ------------------------------------------------------------------ chat

export type StreamHandlers = {
  meta: (m: { mode: Mode; mode_label: string; sources: Source[] }) => void;
  model: (m: ModelInfo) => void;
  token: (t: string) => void;
  replace: (answer: string) => void;
  sources: (s: Source[]) => void;
  paidRequired: (p: { provider: string; model: string; estimated_cost_usd: number }) => void;
  done: (d: { confidence: number; model: ModelInfo | null }) => void;
  error: (message: string) => void;
};

export async function streamChat(
  body: { query: string; session_id: string | null; file_id: number | null; allow_paid: boolean },
  on: StreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const res = await request("/api/chat/stream", { method: "POST", body: JSON.stringify(body), signal });
  if (!res.ok || !res.body) throw new ApiError(res.status, await errorMessage(res));

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    let sep: number;
    while ((sep = buf.indexOf("\n\n")) !== -1) {
      const frame = buf.slice(0, sep);
      buf = buf.slice(sep + 2);
      const event = frame.match(/^event: (.+)$/m)?.[1];
      const raw = frame.match(/^data: (.+)$/m)?.[1];
      if (!event || !raw) continue;
      const data = JSON.parse(raw);
      switch (event) {
        case "meta": on.meta(data); break;
        case "model": on.model(data); break;
        case "token": on.token(data.t); break;
        case "replace": on.replace(data.answer); break;
        case "sources": on.sources(data.sources); break;
        case "paid_required": on.paidRequired(data); break;
        case "done": on.done(data); break;
        case "error": on.error(data.message); break;
      }
    }
  }
}
