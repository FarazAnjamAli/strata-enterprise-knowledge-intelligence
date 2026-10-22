"use client";

import { cn } from "@/lib/cn";
import type { TierStatus } from "@/lib/types";

const ORDER_LABEL = ["01", "02", "03"];

export function tierTone(t: TierStatus): "ok" | "down" | "off" {
  if (!t.enabled) return "off";
  return t.healthy ? "ok" : "down";
}

/** Compact sidebar view of the three tiers, top to bottom in routing order. */
export function TierStackMini({ tiers }: { tiers: TierStatus[] | undefined }) {
  const rows = sortTiers(tiers);
  return (
    <div className="space-y-1">
      {rows.map((t, i) => {
        const tone = tierTone(t);
        return (
          <div key={t.tier} className="flex items-center gap-2.5 text-[12.5px]" title={`${t.provider} · ${t.model}`}>
            <span className="w-4 font-mono text-[10px] text-ink-3">{ORDER_LABEL[i]}</span>
            <span
              className={cn(
                "h-[7px] w-[18px] -skew-x-[30deg]",
                tone === "ok" && "bg-lime ring-1 ring-ink",
                tone === "down" && "bg-danger",
                tone === "off" && "border border-dashed border-line-strong",
              )}
            />
            <span className={cn("flex-1 truncate", tone === "off" ? "text-ink-3" : "text-ink")}>{t.tier_label}</span>
            <span className={cn("font-mono text-[10px] uppercase", tone === "ok" ? "text-ink-2" : tone === "down" ? "text-danger" : "text-ink-3")}>
              {tone === "ok" ? "up" : tone === "down" ? "down" : "off"}
            </span>
          </div>
        );
      })}
      {!tiers && [0, 1, 2].map((i) => <div key={i} className="h-[18px] animate-pulse rounded-xs bg-wash" />)}
    </div>
  );
}

export function sortTiers(tiers: TierStatus[] | undefined): TierStatus[] {
  if (!tiers) return [];
  return [...tiers].sort((a, b) => (a.position ?? 9) - (b.position ?? 9));
}
