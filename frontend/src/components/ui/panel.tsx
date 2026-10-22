"use client";

import { motion } from "motion/react";
import { cn } from "@/lib/cn";

export function Panel({
  title,
  eyebrow,
  action,
  children,
  className,
  bodyClassName,
}: {
  title?: React.ReactNode;
  eyebrow?: string;
  action?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  bodyClassName?: string;
}) {
  return (
    <section className={cn("rounded-sm border border-line bg-white", className)}>
      {(title || action) && (
        <header className="flex items-center justify-between gap-4 border-b border-line px-5 py-3.5">
          <div className="min-w-0">
            {eyebrow && <p className="font-mono text-2xs uppercase text-ink-3">{eyebrow}</p>}
            {title && <h2 className="truncate text-[15px] font-medium tracking-[-0.01em] text-ink">{title}</h2>}
          </div>
          {action}
        </header>
      )}
      <div className={cn("p-5", bodyClassName)}>{children}</div>
    </section>
  );
}

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow?: string;
  title: string;
  description?: React.ReactNode;
  actions?: React.ReactNode;
}) {
  return (
    <div className="relative mb-8 flex flex-wrap items-end justify-between gap-4 pb-6">
      <div className="max-w-2xl">
        {eyebrow && (
          <motion.p
            initial={{ opacity: 0, x: -6 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.4 }}
            className="mb-2 flex items-center gap-2 font-mono text-2xs uppercase text-ink-2"
          >
            <motion.span
              initial={{ width: 0 }}
              animate={{ width: 16 }}
              transition={{ duration: 0.45, delay: 0.1 }}
              className="h-[3px] bg-lime ring-1 ring-ink"
            />
            {eyebrow}
          </motion.p>
        )}
        <motion.h1
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.05, ease: [0.2, 0.7, 0.2, 1] }}
          className="text-[34px] font-medium leading-tight tracking-[-0.02em] text-ink"
        >
          {title}
        </motion.h1>
        {description && (
          <motion.p
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.5, delay: 0.15 }}
            className="mt-2 text-[15px] leading-relaxed text-ink-2"
          >
            {description}
          </motion.p>
        )}
      </div>
      {actions && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.2 }} className="flex items-center gap-2">
          {actions}
        </motion.div>
      )}
      {/* rule draws in from the left */}
      <motion.span
        initial={{ scaleX: 0 }}
        animate={{ scaleX: 1 }}
        transition={{ duration: 0.8, delay: 0.1, ease: [0.2, 0.7, 0.2, 1] }}
        className="absolute bottom-0 left-0 right-0 h-px origin-left bg-line"
      />
      <motion.span
        initial={{ scaleX: 0 }}
        animate={{ scaleX: 1 }}
        transition={{ duration: 0.6, delay: 0.5, ease: [0.2, 0.7, 0.2, 1] }}
        className="absolute bottom-0 left-0 h-[2px] w-16 origin-left bg-ink"
      />
    </div>
  );
}

export function Stat({
  label,
  value,
  hint,
  accent,
}: {
  label: string;
  value: React.ReactNode;
  hint?: React.ReactNode;
  accent?: boolean;
}) {
  return (
    <div className={cn("relative border-line p-5", accent ? "bg-ink text-white" : "bg-white")}>
      <p className={cn("font-mono text-2xs uppercase", accent ? "text-lime" : "text-ink-2")}>{label}</p>
      <p className={cn("mt-3 text-[32px] font-medium leading-none tracking-[-0.02em] tabular-nums", accent ? "text-white" : "text-ink")}>
        {value}
      </p>
      {hint && <p className={cn("mt-2 text-xs", accent ? "text-white/80" : "text-ink-3")}>{hint}</p>}
    </div>
  );
}
