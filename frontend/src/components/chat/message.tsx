"use client";

import { Check, Copy, Download, FileText, Sparkles } from "lucide-react";
import { motion } from "motion/react";
import { useEffect, useState } from "react";
import { TierLoader } from "@/components/motion";
import { Mark } from "@/components/brand";
import { Button } from "@/components/ui/button";
import { openFile } from "@/lib/api";
import { cn } from "@/lib/cn";
import type { Message } from "@/lib/conversations";
import { usd } from "@/lib/format";
import type { ModelInfo, Source } from "@/lib/types";
import { Markdown } from "./markdown";

export function ModelBadge({ model }: { model: ModelInfo }) {
  const tone =
    model.tier === "local"
      ? "border-ink bg-lime text-ink"
      : model.tier === "free"
        ? "border-line-strong bg-white text-ink"
        : "border-ink bg-ink text-lime";
  return (
    <span className={cn("inline-flex h-[22px] items-center gap-1.5 rounded-xs border px-2 font-mono text-[11px]", tone)} title={`${model.provider} · ${model.model}`}>
      <span className="h-[5px] w-[10px] -skew-x-[30deg] bg-current" />
      {model.tier_label}
      <span className="opacity-70">· {model.model}</span>
    </span>
  );
}

function Confidence({ value }: { value: number }) {
  const bars = Math.round(value / 20);
  return (
    <span className="inline-flex items-center gap-1.5 font-mono text-[11px] text-ink-2" title={`Retrieval confidence ${value}%`}>
      <span className="flex gap-[2px]">
        {[0, 1, 2, 3, 4].map((i) => (
          <span key={i} className={cn("h-2.5 w-[3px]", i < bars ? "bg-ink" : "bg-line-strong")} />
        ))}
      </span>
      {value}%
    </span>
  );
}

type SourceGroup = { file_id: number; file_name: string; refs: string[]; snippet: string };

/** One card per document, listing every page/section the answer drew on. */
function group(sources: Source[]): SourceGroup[] {
  const map = new Map<number, SourceGroup>();
  for (const s of sources) {
    const ref = [s.page && `p. ${s.page}`, s.section].filter(Boolean).join(" · ");
    const g = map.get(s.file_id) ?? { file_id: s.file_id, file_name: s.file_name, refs: [], snippet: s.snippet };
    if (ref && !g.refs.includes(ref)) g.refs.push(ref);
    map.set(s.file_id, g);
  }
  return [...map.values()];
}

function Sources({ sources }: { sources: Source[] }) {
  if (!sources.length) return null;
  const groups = group(sources);
  return (
    <div className="mt-5">
      <p className="mb-2 font-mono text-2xs uppercase text-ink-2">
        Sources · {groups.length} {groups.length === 1 ? "document" : "documents"}
      </p>
      <div className="grid gap-2 sm:grid-cols-2">
        {groups.map((s, i) => (
          <motion.button
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.08 * i, duration: 0.35 }}
            key={s.file_id}
            onClick={() => void openFile(s.file_id)}
            className="group flex items-start gap-3 rounded-sm border border-line bg-white p-3 text-left transition-all hover:border-ink hover:shadow-[2px_2px_0_0_#C6FF00]"
            title={s.snippet}
          >
            <span className="grid h-5 w-5 shrink-0 place-items-center rounded-xs bg-ink font-mono text-[10px] text-lime">{i + 1}</span>
            <span className="min-w-0 flex-1">
              <span className="block truncate text-[13px] font-medium text-ink group-hover:underline">{s.file_name}</span>
              <span className="block truncate font-mono text-[11px] text-ink-2">{s.refs.join(", ") || "whole document"}</span>
            </span>
            <FileText className="mt-0.5 h-3.5 w-3.5 shrink-0 text-ink-3 group-hover:text-ink" strokeWidth={1.5} />
          </motion.button>
        ))}
      </div>
    </div>
  );
}

const enter = {
  initial: { opacity: 0, y: 12 },
  animate: { opacity: 1, y: 0 },
  transition: { duration: 0.4, ease: [0.2, 0.7, 0.2, 1] as const },
};

const STEPS = ["Searching your documents", "Ranking passages", "Routing to the best available model", "Writing the answer"];

function Thinking() {
  const [i, setI] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setI((x) => Math.min(x + 1, STEPS.length - 1)), 1100);
    return () => clearInterval(t);
  }, []);
  return (
    <div className="flex items-center gap-3 py-1">
      <TierLoader />
      <motion.span key={i} initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} className="text-sm text-ink-2">
        {STEPS[i]}
        <span className="animate-blink">…</span>
      </motion.span>
    </div>
  );
}

export function UserMessage({ m }: { m: Extract<Message, { role: "user" }> }) {
  return (
    <motion.div {...enter} className="flex justify-end">
      <div className="max-w-[78%]">
        {m.fileName && (
          <p className="mb-1.5 text-right font-mono text-[11px] text-ink-2">
            scoped to <span className="text-ink">{m.fileName}</span>
          </p>
        )}
        <div className="rounded-sm border border-line bg-wash px-4 py-2.5 text-[15px] leading-relaxed text-ink">{m.text}</div>
      </div>
    </motion.div>
  );
}

export function AssistantMessage({
  m,
  onApprovePaid,
  onDeclinePaid,
}: {
  m: Extract<Message, { role: "assistant" }>;
  onApprovePaid: () => void;
  onDeclinePaid: () => void;
}) {
  const [copied, setCopied] = useState(false);
  const streaming = !!m.pending && !m.paid;
  const thinking = streaming && !m.text;
  const general = m.mode === "general";

  return (
    <motion.div {...enter} className="flex gap-4">
      <Mark className="mt-0.5 h-7 w-7 shrink-0" animated={streaming} />
      <div className="min-w-0 flex-1">
        <div className="mb-2 flex min-h-[22px] flex-wrap items-center gap-2">
          {m.modeLabel && (
            <span className={cn("font-mono text-[11px] uppercase", general ? "text-amber" : "text-ink-2")}>{m.modeLabel}</span>
          )}
          {m.model && (
            <motion.span initial={{ opacity: 0, scale: 0.85 }} animate={{ opacity: 1, scale: 1 }} transition={{ type: "spring", stiffness: 500, damping: 28 }}>
              <ModelBadge model={m.model} />
            </motion.span>
          )}
          {!!m.confidence && m.confidence > 0 && <Confidence value={m.confidence} />}
        </div>

        {thinking ? (
          <Thinking />
        ) : (
          m.text && <Markdown text={m.text} streaming={streaming} />
        )}

        {m.image && (
          <div className="mt-3 overflow-hidden rounded-sm border border-line">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={m.image} alt="Generated diagram" className="w-full" />
            <div className="flex justify-end border-t border-line bg-paper px-3 py-2">
              <a href={m.image} download="diagram.png">
                <Button size="sm" variant="ghost">
                  <Download className="h-3.5 w-3.5" /> Download
                </Button>
              </a>
            </div>
          </div>
        )}

        {m.paid && (
          <motion.div
            initial={{ opacity: 0, y: 10, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            transition={{ duration: 0.4, ease: [0.2, 0.7, 0.2, 1] }}
            className="mt-1 rounded-sm border border-ink bg-white p-4 shadow-[3px_3px_0_0_#C6FF00]"
          >
            <div className="flex items-start gap-3">
              <span className="grid h-7 w-7 shrink-0 place-items-center rounded-xs bg-ink text-lime">
                <Sparkles className="h-3.5 w-3.5" strokeWidth={1.75} />
              </span>
              <div className="flex-1">
                <p className="text-[15px] font-medium text-ink">Use the premium model for this answer?</p>
                <p className="mt-1 text-sm leading-relaxed text-ink-2">
                  The local model and free API are unavailable right now. {m.paid.provider} ({m.paid.model}) can answer for an
                  estimated cost <span className="font-mono text-ink">{usd(m.paid.estimated_cost_usd)}</span>. Financial figures are
                  masked before anything is sent.
                </p>
                <div className="mt-3.5 flex gap-2">
                  <Button size="sm" variant="primary" onClick={onApprovePaid}>
                    Use premium
                  </Button>
                  <Button size="sm" variant="secondary" onClick={onDeclinePaid}>
                    Not now
                  </Button>
                </div>
              </div>
            </div>
          </motion.div>
        )}

        {m.error && (
          <div className="mt-2 rounded-sm border border-danger/40 bg-danger-soft px-3.5 py-2.5 text-sm text-danger">{m.error}</div>
        )}

        {!m.pending && <Sources sources={m.sources} />}

        {!m.pending && m.text && (
          <div className="mt-3 flex items-center gap-1">
            <button
              onClick={() => {
                void navigator.clipboard.writeText(m.text);
                setCopied(true);
                setTimeout(() => setCopied(false), 1400);
              }}
              className="inline-flex h-7 items-center gap-1.5 rounded-xs px-2 text-xs text-ink-2 hover:bg-wash hover:text-ink"
            >
              {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" strokeWidth={1.5} />}
              {copied ? "Copied" : "Copy"}
            </button>
          </div>
        )}
      </div>
    </motion.div>
  );
}
