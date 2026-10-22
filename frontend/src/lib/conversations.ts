"use client";

import type { ModelInfo, Mode, Source } from "./types";

export type Message =
  | { id: string; role: "user"; text: string; ts: number; fileName?: string }
  | {
      id: string;
      role: "assistant";
      text: string;
      ts: number;
      mode?: Mode;
      modeLabel?: string;
      model?: ModelInfo | null;
      confidence?: number;
      sources: Source[];
      image?: string;
      pending?: boolean;
      paid?: { provider: string; model: string; estimated_cost_usd: number; query: string; fileId: number | null };
      error?: string;
    };

export type Conversation = { id: string; title: string; updated: number; messages: Message[] };

const MAX_CONVERSATIONS = 50;
const key = (userId: number) => `strata.conversations.v1.${userId}`;

export function loadConversations(userId: number): Conversation[] {
  try {
    const raw = localStorage.getItem(key(userId));
    return raw ? (JSON.parse(raw) as Conversation[]) : [];
  } catch {
    return [];
  }
}

export function saveConversation(userId: number, conv: Conversation): Conversation[] {
  // images are large base64 blobs - kept in memory only, never persisted
  const slim: Conversation = {
    ...conv,
    messages: conv.messages
      .filter((m) => !(m.role === "assistant" && m.pending))
      .map((m) => (m.role === "assistant" && m.image ? { ...m, image: undefined, text: m.text || "_Generated diagram (not stored)_" } : m)),
  };
  const others = loadConversations(userId).filter((c) => c.id !== conv.id);
  const next = [slim, ...others].sort((a, b) => b.updated - a.updated).slice(0, MAX_CONVERSATIONS);
  try {
    localStorage.setItem(key(userId), JSON.stringify(next));
  } catch {
    /* quota or disabled storage - history is a convenience */
  }
  return next;
}

export function deleteConversation(userId: number, id: string): Conversation[] {
  const next = loadConversations(userId).filter((c) => c.id !== id);
  try {
    localStorage.setItem(key(userId), JSON.stringify(next));
  } catch {
    /* ignore */
  }
  return next;
}

export const newId = () =>
  typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : Math.random().toString(36).slice(2) + Date.now().toString(36);
