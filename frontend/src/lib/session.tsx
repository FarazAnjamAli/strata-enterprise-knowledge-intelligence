"use client";

import { createContext, useCallback, useContext, useMemo } from "react";
import useSWR from "swr";
import { fetcher, post } from "./api";
import type { Profile, SystemStatus } from "./types";

type Session = {
  profile: Profile | null;
  status: SystemStatus | null;
  isAdmin: boolean;
  isHead: boolean; // Department Head or Admin
  refreshStatus: () => void;
  signOut: () => Promise<void>;
};

const Ctx = createContext<Session | null>(null);

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const { data: profile } = useSWR<Profile>("/api/auth/me", fetcher, { revalidateOnFocus: false });
  const { data: status, mutate } = useSWR<SystemStatus>("/api/system/status", fetcher, {
    refreshInterval: 30_000,
  });

  const signOut = useCallback(async () => {
    try {
      await post("/api/auth/logout");
    } finally {
      try {
        sessionStorage.clear();
      } catch {
        /* storage unavailable */
      }
      window.location.href = "/login";
    }
  }, []);

  const value = useMemo<Session>(
    () => ({
      profile: profile ?? null,
      status: status ?? null,
      isAdmin: profile?.role === "Admin",
      isHead: profile?.role === "Admin" || profile?.role === "Department Head",
      refreshStatus: () => void mutate(),
      signOut,
    }),
    [profile, status, mutate, signOut],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useSession(): Session {
  const s = useContext(Ctx);
  if (!s) throw new Error("useSession outside SessionProvider");
  return s;
}
