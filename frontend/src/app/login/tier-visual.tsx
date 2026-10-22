"use client";

import { motion } from "motion/react";
import { CropMarks } from "@/components/motion";

/** Right-hand panel on the sign-in page: a question falls through three
 *  tiers until one answers. Animated, but decorative only. */
const TIERS = [
  { n: "01", name: "Local model", detail: "Runs on your hardware. Data never leaves.", state: "Answering" },
  { n: "02", name: "Free API", detail: "Automatic fallback. Figures masked first.", state: "Standby" },
  { n: "03", name: "Premium API", detail: "Last resort, only with your approval.", state: "On approval" },
];

const FORMATS = ["PDF", "DOCX", "XLSX", "CSV", "MARKDOWN", "JSON", "XML", "PNG · OCR", "JPG · OCR", "MP4 · METADATA", "TXT"];

const ease = [0.2, 0.7, 0.2, 1] as const;

export function TierVisual() {
  return (
    <div className="relative hidden overflow-hidden border-l border-line bg-paper lg:block">
      <div className="grid-lines absolute inset-0 opacity-60" />
      <div className="relative flex h-full flex-col justify-between p-14 xl:p-20">
        <div className="max-w-xl">
          <motion.p
            initial={{ opacity: 0, x: -8 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.5, ease }}
            className="font-mono text-2xs uppercase text-ink-2"
          >
            Three-tier retrieval-augmented generation
          </motion.p>
          <motion.h2
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, delay: 0.1, ease }}
            className="mt-5 text-[44px] font-medium leading-[1.04] tracking-[-0.02em] text-ink xl:text-[56px]"
          >
            Answers grounded in{" "}
            <span className="relative inline-block">
              <motion.span
                initial={{ scaleX: 0 }}
                animate={{ scaleX: 1 }}
                transition={{ duration: 0.7, delay: 0.75, ease }}
                className="absolute inset-x-[-4px] bottom-[6%] top-[52%] origin-left -skew-x-12 bg-lime"
              />
              <span className="relative">your documents</span>
            </span>
            .
          </motion.h2>
        </div>

        <div className="relative max-w-xl">
          {/* the route a question takes */}
          <div className="space-y-3">
            {TIERS.map((t, i) => (
              <motion.div
                key={t.n}
                initial={{ opacity: 0, x: 24 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ duration: 0.6, delay: 0.35 + i * 0.12, ease }}
                className="relative flex items-center gap-5 rounded-sm border border-line bg-white px-5 py-4"
                style={{ marginLeft: `${i * 28}px` }}
              >
                {i === 0 && <CropMarks />}
                <span className="font-mono text-xs text-ink-3">{t.n}</span>
                <span className={`h-2.5 w-9 -skew-x-[30deg] ${i === 0 ? "bg-lime ring-1 ring-ink" : "bg-ink"}`} />
                <div className="min-w-0 flex-1">
                  <p className="text-[15px] font-medium text-ink">{t.name}</p>
                  <p className="text-[13px] text-ink-2">{t.detail}</p>
                </div>
                <span
                  className={`flex items-center gap-1.5 rounded-xs border px-2 py-1 font-mono text-[10.5px] uppercase ${
                    i === 0 ? "border-ink bg-lime text-ink" : "border-line-strong bg-white text-ink-2"
                  }`}
                >
                    {t.state}
                </span>
              </motion.div>
            ))}
          </div>
        </div>

        <div className="space-y-5">
          <div className="relative overflow-hidden border-y border-line bg-white py-2.5 [mask-image:linear-gradient(90deg,transparent,#000_10%,#000_90%,transparent)]">
            <div className="flex w-max animate-marquee gap-8 font-mono text-[11px] uppercase text-ink-2">
              {[...FORMATS, ...FORMATS].map((f, i) => (
                <span key={i} className="flex items-center gap-8">
                  {f}
                  <span className="h-1 w-1 bg-lime ring-1 ring-ink" />
                </span>
              ))}
            </div>
          </div>
          <div className="flex items-center gap-8 font-mono text-[11px] uppercase text-ink-2">
            <span>Hybrid search · pgvector + full-text</span>
            <span>Role-based access</span>
            <span>Audited</span>
          </div>
        </div>
      </div>
    </div>
  );
}
