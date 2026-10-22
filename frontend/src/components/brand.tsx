"use client";

import { motion } from "motion/react";
import { cn } from "@/lib/cn";

/** The Strata mark: three stacked tiers - local, free, premium - with the
 *  top one lit. Drawn inline so it stays crisp at any size. */
const BARS = ["M12.5 7.5H26L23.5 11H10Z", "M9.25 14.25H22.75L20.25 17.75H6.75Z", "M6 21H19.5L17 24.5H3.5Z"];

export function Mark({ className, inverted, animated }: { className?: string; inverted?: boolean; animated?: boolean }) {
  const ink = inverted ? "#0A0A0A" : "#FFFFFF";
  return (
    <svg viewBox="0 0 32 32" className={cn("h-7 w-7", className)} aria-hidden>
      {!inverted && <rect width="32" height="32" rx="3" fill="#0A0A0A" />}
      {BARS.map((d, i) =>
        animated ? (
          <motion.path
            key={d}
            d={d}
            fill={i === 0 ? "#C6FF00" : ink}
            initial={{ x: -10, opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            transition={{ duration: 0.5, delay: 0.15 + (2 - i) * 0.1, ease: [0.2, 0.7, 0.2, 1] }}
          />
        ) : (
          <path key={d} d={d} fill={i === 0 ? "#C6FF00" : ink} />
        ),
      )}
    </svg>
  );
}

export function Logo({ className, size = "md", animated }: { className?: string; size?: "sm" | "md" | "lg"; animated?: boolean }) {
  const s = { sm: ["h-6 w-6", "text-[17px]"], md: ["h-7 w-7", "text-[19px]"], lg: ["h-10 w-10", "text-[28px]"] }[size];
  return (
    <span className={cn("inline-flex items-center gap-2.5", className)}>
      <Mark className={s[0]} animated={animated} />
      <span className={cn("font-medium leading-none tracking-[-0.02em] text-ink", s[1])}>
        strata<span className="text-ink-3">.</span>
      </span>
    </span>
  );
}
