"use client";

import { MotionConfig } from "motion/react";
import { SWRConfig } from "swr";
import { ToastProvider } from "@/components/ui/toast";
import { fetcher } from "@/lib/api";
import { SessionProvider } from "@/lib/session";

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <MotionConfig reducedMotion="user">
      <SWRConfig value={{ fetcher, shouldRetryOnError: false, revalidateOnFocus: true }}>
        <ToastProvider>
          <SessionProvider>{children}</SessionProvider>
        </ToastProvider>
      </SWRConfig>
    </MotionConfig>
  );
}
