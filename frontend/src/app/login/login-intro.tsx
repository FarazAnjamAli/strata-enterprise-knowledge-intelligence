"use client";

import { motion } from "motion/react";

const ease = [0.2, 0.7, 0.2, 1] as const;

export function LoginIntro() {
  return (
    <>
      <motion.p
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.45, ease }}
        className="mb-3 flex items-center gap-2 font-mono text-2xs uppercase text-ink-2"
      >
        <motion.span
          initial={{ width: 0 }}
          animate={{ width: 16 }}
          transition={{ duration: 0.5, delay: 0.2, ease }}
          className="h-[3px] bg-lime ring-1 ring-ink"
        />
        Secure workspace
      </motion.p>
      <motion.h1
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.55, delay: 0.05, ease }}
        className="text-[34px] font-medium leading-[1.1] tracking-[-0.02em] text-ink"
      >
        Sign in to Strata
      </motion.h1>
      <motion.p
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.55, delay: 0.12, ease }}
        className="mt-3 text-[15px] leading-relaxed text-ink-2"
      >
        Ask questions across your organization&apos;s documents. Every answer comes with its sources.
      </motion.p>
    </>
  );
}
