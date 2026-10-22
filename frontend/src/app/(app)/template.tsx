"use client";

import { motion } from "motion/react";

/** Re-mounts on every navigation: a lime progress sweep across the top
 *  edge plus a soft enter for the page body. */
export default function Template({ children }: { children: React.ReactNode }) {
  return (
    <>
      <span aria-hidden className="pointer-events-none fixed left-0 right-0 top-0 z-[70] h-[2px] origin-left animate-sweep bg-lime" />
      <motion.div
        className="flex min-h-0 flex-1 flex-col"
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, ease: [0.2, 0.7, 0.2, 1] }}
      >
        {children}
      </motion.div>
    </>
  );
}
