"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export function Markdown({ text, streaming }: { text: string; streaming?: boolean }) {
  return (
    <div className="prose-strata">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={{ a: (p) => <a {...p} target="_blank" rel="noreferrer" /> }}>
        {text}
      </ReactMarkdown>
      {streaming && <span className="ml-0.5 inline-block h-[1.05em] w-[7px] translate-y-[3px] animate-blink bg-ink" />}
    </div>
  );
}
