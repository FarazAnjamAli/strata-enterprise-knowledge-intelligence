"use client";

import { ArrowUp, FileText, ImageIcon, PanelLeft, Plus, Square, Trash2, X } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useRouter, useSearchParams } from "next/navigation";
import { Mark } from "@/components/brand";
import { CropMarks } from "@/components/motion";
import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import useSWR from "swr";
import { AssistantMessage, UserMessage } from "@/components/chat/message";
import { FileIcon } from "@/components/files/file-icon";
import { Button } from "@/components/ui/button";
import { ApiError, api, del, streamChat } from "@/lib/api";
import { cn } from "@/lib/cn";
import {
  type Conversation,
  type Message,
  deleteConversation,
  loadConversations,
  newId,
  saveConversation,
} from "@/lib/conversations";
import { ago } from "@/lib/format";
import { useSession } from "@/lib/session";
import type { FileOut } from "@/lib/types";

type Assistant = Extract<Message, { role: "assistant" }>;

const SUGGESTIONS = [
  "Summarize the key points of our latest policy documents",
  "What are the approval steps for a purchase request?",
  "Compare the figures in the two most recent reports",
  "Who is responsible for incident escalation?",
];

function ChatInner() {
  const router = useRouter();
  const params = useSearchParams();
  const { profile, status } = useSession();
  const [convs, setConvs] = useState<Conversation[]>([]);
  const [conv, setConv] = useState<Conversation>(() => ({ id: newId(), title: "New chat", updated: Date.now(), messages: [] }));
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [scope, setScope] = useState<{ id: number; name: string } | null>(null);
  const [showList, setShowList] = useState(true);
  const [hi, setHi] = useState(0);
  const abortRef = useRef<AbortController | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const bootRef = useRef(false);
  const convRef = useRef(conv);
  useEffect(() => {
    convRef.current = conv;
  }, [conv]);

  const slash = input.startsWith("/");
  const lower = input.toLowerCase();
  const fileTerm = lower.startsWith("/file") ? input.slice(5).trim().toLowerCase() : null;
  const imageArg = lower.startsWith("/image") ? input.slice(6).trim() : null;
  const { data: files } = useSWR<FileOut[]>(slash ? "/api/files?limit=1000" : null);

  const commands = useMemo(
    () => [
      { cmd: "/file", hint: "Ask one document in isolation", icon: FileText },
      ...(status?.image_generation ? [{ cmd: "/image", hint: "Generate a process diagram", icon: ImageIcon }] : []),
    ],
    [status?.image_generation],
  );
  const fileMatches = useMemo(
    () =>
      fileTerm !== null
        ? (files ?? []).filter((f) => f.index_status === "ready" && f.name.toLowerCase().includes(fileTerm)).slice(0, 8)
        : [],
    [files, fileTerm],
  );
  const menuCount = fileTerm !== null ? fileMatches.length : imageArg !== null ? 0 : slash ? commands.length : 0;
  useEffect(() => setHi(0), [input]);

  // ---------------------------------------------------------- persistence
  const persist = useCallback(
    (c: Conversation) => {
      if (!profile || !c.messages.some((m) => m.role === "user")) return;
      setConvs(saveConversation(profile.id, c));
    },
    [profile],
  );

  useEffect(() => {
    if (!profile || bootRef.current) return;
    bootRef.current = true;
    const list = loadConversations(profile.id);
    setConvs(list);
    const cid = params.get("c");
    const found = cid ? list.find((c) => c.id === cid) : null;
    if (found) setConv(found);
    const fid = params.get("file");
    if (fid) {
      setScope({ id: Number(fid), name: params.get("name") ?? `file #${fid}` });
      router.replace("/chat");
    }
    const q = params.get("q");
    if (q) {
      router.replace("/chat");
      void ask(q, null, false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [profile]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [conv.messages]);

  useEffect(() => {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = "0px";
    el.style.height = `${Math.min(200, el.scrollHeight)}px`;
  }, [input]);

  // ------------------------------------------------------------- helpers
  const update = useCallback((fn: (c: Conversation) => Conversation, save = false) => {
    setConv((prev) => {
      const next = fn(prev);
      if (save) queueMicrotask(() => persist(next));
      return next;
    });
  }, [persist]);

  const patchMsg = useCallback(
    (id: string, fn: (m: Assistant) => Assistant, save = false) =>
      update((c) => ({ ...c, messages: c.messages.map((m) => (m.id === id && m.role === "assistant" ? fn(m) : m)) }), save),
    [update],
  );

  function newChat() {
    abortRef.current?.abort();
    setConv({ id: newId(), title: "New chat", updated: Date.now(), messages: [] });
    setScope(null);
    setInput("");
    inputRef.current?.focus();
  }

  // ------------------------------------------------------------------ ask
  async function ask(raw: string, fileId: number | null, allowPaid: boolean, reuseId?: string) {
    const q = raw.trim();
    if (!q || busy) return;
    setBusy(true);
    setInput("");
    const aid = reuseId ?? newId();
    const fileName = fileId !== null ? scope?.name : undefined;
    if (!reuseId) {
      update((c) => ({
        ...c,
        title: c.messages.length ? c.title : q.slice(0, 80),
        updated: Date.now(),
        messages: [
          ...c.messages,
          { id: newId(), role: "user", text: q, ts: Date.now(), fileName },
          { id: aid, role: "assistant", text: "", ts: Date.now(), sources: [], pending: true },
        ],
      }));
    } else {
      patchMsg(aid, (m) => ({ ...m, paid: undefined, pending: true, text: "", error: undefined }));
    }

    const ctrl = new AbortController();
    abortRef.current = ctrl;
    const convId = convRef.current.id;
    try {
      await streamChat(
        { query: q, session_id: convId || null, file_id: fileId, allow_paid: allowPaid },
        {
          meta: (d) => patchMsg(aid, (m) => ({ ...m, mode: d.mode, modeLabel: d.mode_label, sources: d.sources })),
          model: (d) => patchMsg(aid, (m) => ({ ...m, model: d })),
          token: (t) => patchMsg(aid, (m) => ({ ...m, text: m.text + t })),
          replace: (a) => patchMsg(aid, (m) => ({ ...m, text: a })),
          sources: (s) => patchMsg(aid, (m) => ({ ...m, sources: s })),
          paidRequired: (p) => patchMsg(aid, (m) => ({ ...m, paid: { ...p, query: q, fileId } })),
          error: (e) => patchMsg(aid, (m) => ({ ...m, error: e })),
          done: (d) =>
            patchMsg(aid, (m) => ({ ...m, pending: false, confidence: d.confidence, model: d.model ?? m.model }), true),
        },
        ctrl.signal,
      );
    } catch (err) {
      const aborted = err instanceof DOMException && err.name === "AbortError";
      patchMsg(
        aid,
        (m) => ({
          ...m,
          pending: false,
          error: aborted ? undefined : err instanceof ApiError ? err.message : "Something went wrong. Try again.",
          text: aborted ? m.text || "_Stopped._" : m.text,
        }),
        true,
      );
    } finally {
      setBusy(false);
      abortRef.current = null;
    }
  }

  async function makeImage(prompt: string) {
    if (!prompt || busy) return;
    setBusy(true);
    setInput("");
    const aid = newId();
    update((c) => ({
      ...c,
      title: c.messages.length ? c.title : `Diagram: ${prompt.slice(0, 60)}`,
      updated: Date.now(),
      messages: [
        ...c.messages,
        { id: newId(), role: "user", text: `/image ${prompt}`, ts: Date.now() },
        { id: aid, role: "assistant", text: "", ts: Date.now(), sources: [], pending: true, modeLabel: "Diagram" },
      ],
    }));
    try {
      const img = await api<{ image_base64: string; mime_type: string; text: string | null }>("/api/image", {
        method: "POST",
        body: JSON.stringify({ prompt }),
      });
      patchMsg(aid, (m) => ({ ...m, pending: false, text: img.text ?? "", image: `data:${img.mime_type};base64,${img.image_base64}` }), true);
    } catch (err) {
      patchMsg(aid, (m) => ({ ...m, pending: false, error: err instanceof ApiError ? err.message : "Diagram generation failed." }), true);
    } finally {
      setBusy(false);
    }
  }

  function submit(e?: React.FormEvent) {
    e?.preventDefault();
    if (imageArg !== null) return void makeImage(imageArg);
    if (fileTerm !== null) {
      const f = fileMatches[hi] ?? fileMatches[0];
      if (f) {
        setScope({ id: f.id, name: f.name });
        setInput("");
      }
      return;
    }
    if (slash) {
      const c = commands[hi] ?? commands[0];
      if (c) setInput(`${c.cmd} `);
      return;
    }
    void ask(input, scope?.id ?? null, false);
  }

  function onKey(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (slash && menuCount > 0 && (e.key === "ArrowDown" || e.key === "ArrowUp")) {
      e.preventDefault();
      setHi((h) => (h + (e.key === "ArrowDown" ? 1 : -1) + menuCount) % menuCount);
      return;
    }
    if (e.key === "Escape") {
      if (busy) abortRef.current?.abort();
      else setInput("");
      return;
    }
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      submit();
    }
  }

  function openConv(c: Conversation) {
    abortRef.current?.abort();
    setConv(c);
    setScope(null);
  }

  function removeConv(id: string) {
    if (!profile) return;
    setConvs(deleteConversation(profile.id, id));
    void del(`/api/chat/sessions/${id}`).catch(() => {});
    if (conv.id === id) newChat();
  }

  const empty = conv.messages.length === 0;

  return (
    <div className="flex h-full min-h-0 flex-1">
      {/* ------------------------------------------------ conversation list */}
      <aside className={cn("flex w-[268px] shrink-0 flex-col border-r border-line bg-paper transition-all", !showList && "-ml-[268px]")}>
        <div className="flex h-16 items-center justify-between border-b border-line px-4">
          <p className="font-mono text-2xs uppercase text-ink-2">Conversations</p>
          <Button size="sm" variant="primary" onClick={newChat}>
            <Plus className="h-3.5 w-3.5" strokeWidth={2} /> New
          </Button>
        </div>
        <div className="flex-1 overflow-y-auto p-2">
          {convs.length === 0 && <p className="px-3 py-6 text-center text-[13px] text-ink-2">Your chats will appear here.</p>}
          <AnimatePresence initial={false}>
          {convs.map((c) => (
            <motion.div
              layout
              key={c.id}
              initial={{ opacity: 0, x: -10 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -20, height: 0 }}
              transition={{ duration: 0.25 }}
              className={cn(
                "group flex items-center gap-1 rounded-xs pr-1 transition-colors",
                c.id === conv.id ? "bg-white ring-1 ring-line-strong" : "hover:bg-white",
              )}
            >
              <button onClick={() => openConv(c)} className="min-w-0 flex-1 px-3 py-2.5 text-left">
                <p className={cn("truncate text-[13px]", c.id === conv.id ? "font-medium text-ink" : "text-ink-2")}>{c.title}</p>
                <p className="mt-0.5 font-mono text-[10.5px] text-ink-3">{ago(new Date(c.updated).toISOString())}</p>
              </button>
              <button
                onClick={() => removeConv(c.id)}
                className="grid h-7 w-7 shrink-0 place-items-center rounded-xs text-ink-3 opacity-0 hover:bg-wash hover:text-danger group-hover:opacity-100"
                aria-label="Delete conversation"
              >
                <Trash2 className="h-3.5 w-3.5" strokeWidth={1.5} />
              </button>
            </motion.div>
          ))}
          </AnimatePresence>
        </div>
      </aside>

      {/* ------------------------------------------------------------ thread */}
      <section className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-16 shrink-0 items-center gap-3 border-b border-line px-5">
          <button
            onClick={() => setShowList((v) => !v)}
            className="grid h-8 w-8 place-items-center rounded-xs text-ink-2 hover:bg-wash hover:text-ink"
            aria-label="Toggle conversation list"
          >
            <PanelLeft className="h-4 w-4" strokeWidth={1.5} />
          </button>
          <h1 className="min-w-0 flex-1 truncate text-[15px] font-medium text-ink">{empty ? "New chat" : conv.title}</h1>
          <span className="hidden font-mono text-[11px] text-ink-3 md:block">Enter to send · Shift+Enter newline · / commands</span>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto">
          <div className="mx-auto w-full max-w-[820px] px-6 py-8">
            {empty ? (
              <div className="relative pt-[6vh]">
                <motion.div
                  initial={{ opacity: 0, scale: 0.9 }}
                  animate={{ opacity: 1, scale: 1 }}
                  transition={{ duration: 0.6, ease: [0.2, 0.7, 0.2, 1] }}
                  className="relative mb-8 inline-grid h-16 w-16 place-items-center border border-line bg-paper"
                >
                  <CropMarks />
                  <Mark animated className="h-9 w-9" />
                </motion.div>
                <motion.p
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.1 }}
                  className="mb-3 flex items-center gap-2 font-mono text-2xs uppercase text-ink-2"
                >
                  <span className="h-[3px] w-4 bg-lime ring-1 ring-ink" /> Assistant
                </motion.p>
                <motion.h2
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.15, duration: 0.5 }}
                  className="text-[38px] font-medium leading-[1.08] tracking-[-0.02em] text-ink"
                >
                  What do you need to{" "}
                  <span className="relative inline-block">
                    <motion.span
                      initial={{ scaleX: 0 }}
                      animate={{ scaleX: 1 }}
                      transition={{ delay: 0.55, duration: 0.6, ease: [0.2, 0.7, 0.2, 1] }}
                      className="absolute inset-x-[-3px] bottom-[8%] top-[55%] origin-left -skew-x-12 bg-lime"
                    />
                    <span className="relative">know</span>
                  </span>
                  ?
                </motion.h2>
                <motion.p
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ delay: 0.3 }}
                  className="mt-3 max-w-lg text-[15px] leading-relaxed text-ink-2"
                >
                  Answers come from the documents you can access, with sources. If nothing matches you&apos;ll be told, and
                  general-knowledge answers are clearly labelled.
                </motion.p>
                <div className="mt-8 grid gap-2 sm:grid-cols-2">
                  {SUGGESTIONS.map((s, i) => (
                    <motion.button
                      key={s}
                      initial={{ opacity: 0, y: 12 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: 0.35 + i * 0.07, duration: 0.45, ease: [0.2, 0.7, 0.2, 1] }}
                      onClick={() => void ask(s, scope?.id ?? null, false)}
                      className="lift group flex items-start gap-3 rounded-sm border border-line bg-white p-4 text-left text-sm text-ink"
                    >
                      <span className="mt-0.5 font-mono text-[10px] text-ink-3">0{i + 1}</span>
                      <span className="flex-1">{s}</span>
                      <span className="text-ink-3 transition-transform group-hover:translate-x-0.5 group-hover:text-ink">→</span>
                    </motion.button>
                  ))}
                </div>
              </div>
            ) : (
              <div className="space-y-8">
                {conv.messages.map((m) =>
                  m.role === "user" ? (
                    <UserMessage key={m.id} m={m} />
                  ) : (
                    <AssistantMessage
                      key={m.id}
                      m={m}
                      onApprovePaid={() => m.paid && void ask(m.paid.query, m.paid.fileId, true, m.id)}
                      onDeclinePaid={() =>
                        patchMsg(m.id, (x) => ({ ...x, paid: undefined, pending: false, text: "Okay, no premium call was made. Try again later, when the local model is back." }), true)
                      }
                    />
                  ),
                )}
              </div>
            )}
            <div ref={bottomRef} className="h-4" />
          </div>
        </div>

        {/* ------------------------------------------------------- composer */}
        <div className="shrink-0 px-6 pb-6">
          <div className="relative mx-auto w-full max-w-[820px]">
            {slash && (menuCount > 0 || fileTerm !== null) && (
              <motion.div
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.18 }}
                className="absolute bottom-full left-0 right-0 mb-2 overflow-hidden rounded-sm border border-ink bg-white shadow-lift"
              >
                <p className="border-b border-line bg-paper px-4 py-2 font-mono text-2xs uppercase text-ink-2">
                  {fileTerm !== null ? "Pick a document" : "Commands"}
                </p>
                {fileTerm !== null ? (
                  fileMatches.length ? (
                    fileMatches.map((f, i) => (
                      <button
                        key={f.id}
                        onMouseEnter={() => setHi(i)}
                        onClick={() => {
                          setScope({ id: f.id, name: f.name });
                          setInput("");
                          inputRef.current?.focus();
                        }}
                        className={cn("flex w-full items-center gap-3 px-4 py-2.5 text-left text-sm", i === hi ? "bg-wash" : "")}
                      >
                        <FileIcon name={f.name} className="h-6 w-6 text-[8px]" />
                        <span className="flex-1 truncate text-ink">{f.name}</span>
                        <span className="font-mono text-[11px] text-ink-3">{f.department ?? "personal"}</span>
                      </button>
                    ))
                  ) : (
                    <p className="px-4 py-3 text-sm text-ink-2">{files ? "No indexed document matches." : "Loading documents…"}</p>
                  )
                ) : (
                  commands.map((c, i) => (
                    <button
                      key={c.cmd}
                      onMouseEnter={() => setHi(i)}
                      onClick={() => setInput(`${c.cmd} `)}
                      className={cn("flex w-full items-center gap-3 px-4 py-2.5 text-left", i === hi ? "bg-wash" : "")}
                    >
                      <c.icon className="h-4 w-4 text-ink" strokeWidth={1.5} />
                      <span className="font-mono text-sm text-ink">{c.cmd}</span>
                      <span className="text-sm text-ink-2">{c.hint}</span>
                    </button>
                  ))
                )}
              </motion.div>
            )}

            <form
              onSubmit={submit}
              className="rounded-sm border border-ink bg-white transition-shadow focus-within:shadow-[4px_4px_0_0_#C6FF00]"
            >
              {scope && (
                <div className="flex items-center gap-2 border-b border-line px-4 py-2">
                  <span className="font-mono text-[11px] uppercase text-ink-2">Only</span>
                  <span className="inline-flex max-w-[60%] items-center gap-1.5 rounded-xs bg-lime px-2 py-0.5 text-[13px] text-ink ring-1 ring-ink">
                    <span className="truncate">{scope.name}</span>
                    <button type="button" onClick={() => setScope(null)} aria-label="Clear file scope">
                      <X className="h-3 w-3" />
                    </button>
                  </span>
                </div>
              )}
              <div className="flex items-end gap-2 p-2 pl-4">
                <textarea
                  ref={inputRef}
                  rows={1}
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={onKey}
                  placeholder={scope ? `Ask about ${scope.name}…` : "Ask a question, or type / for commands"}
                  className="max-h-[200px] min-h-[24px] flex-1 resize-none bg-transparent py-2 text-[15px] leading-6 text-ink placeholder:text-ink-3 focus:outline-none"
                />
                {busy ? (
                  <Button type="button" size="icon" variant="secondary" onClick={() => abortRef.current?.abort()} aria-label="Stop" className="h-9 w-9">
                    <Square className="h-3 w-3 fill-current" />
                  </Button>
                ) : (
                  <Button type="submit" size="icon" variant="primary" disabled={!input.trim()} aria-label="Send" className="h-9 w-9">
                    <ArrowUp className="h-4 w-4" strokeWidth={2} />
                  </Button>
                )}
              </div>
            </form>
            <p className="mt-2 text-center font-mono text-[10.5px] text-ink-3">
              Answers can be wrong. Check the cited sources before acting on them.
            </p>
          </div>
        </div>
      </section>
    </div>
  );
}

export default function ChatPage() {
  return (
    <Suspense>
      <ChatInner />
    </Suspense>
  );
}
