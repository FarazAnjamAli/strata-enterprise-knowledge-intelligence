"use client";

import { cn } from "@/lib/cn";

export function Tabs<T extends string>({
  value,
  onChange,
  items,
  className,
}: {
  value: T;
  onChange: (v: T) => void;
  items: { value: T; label: string; count?: number | null }[];
  className?: string;
}) {
  return (
    <div role="tablist" className={cn("flex items-end gap-6 border-b border-line", className)}>
      {items.map((it) => {
        const active = it.value === value;
        return (
          <button
            key={it.value}
            role="tab"
            aria-selected={active}
            onClick={() => onChange(it.value)}
            className={cn(
              "relative -mb-px flex items-center gap-2 border-b-2 pb-3 pt-1 text-sm transition-colors",
              active ? "border-ink font-medium text-ink" : "border-transparent text-ink-2 hover:text-ink",
            )}
          >
            {it.label}
            {it.count != null && (
              <span
                className={cn(
                  "rounded-xs px-1.5 py-0.5 font-mono text-[10.5px] leading-none",
                  active ? "bg-lime text-ink ring-1 ring-ink" : "bg-wash text-ink-2",
                )}
              >
                {it.count}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}

export function Segmented<T extends string>({
  value,
  onChange,
  items,
  size = "md",
}: {
  value: T;
  onChange: (v: T) => void;
  items: { value: T; label: string }[];
  size?: "sm" | "md";
}) {
  return (
    <div className="inline-flex rounded-sm border border-line-strong bg-white p-0.5">
      {items.map((it) => (
        <button
          key={it.value}
          type="button"
          onClick={() => onChange(it.value)}
          className={cn(
            "rounded-xs px-3 font-medium transition-colors",
            size === "sm" ? "h-7 text-xs" : "h-8 text-[13px]",
            it.value === value ? "bg-ink text-white" : "text-ink-2 hover:text-ink",
          )}
        >
          {it.label}
        </button>
      ))}
    </div>
  );
}
