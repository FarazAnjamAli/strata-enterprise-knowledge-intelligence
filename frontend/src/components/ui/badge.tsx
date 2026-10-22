import { cn } from "@/lib/cn";

type Tone = "neutral" | "lime" | "ink" | "danger" | "amber" | "outline";

const tones: Record<Tone, string> = {
  neutral: "bg-wash text-ink-2 border-line",
  lime: "bg-lime text-ink border-ink",
  ink: "bg-ink text-white border-ink",
  danger: "bg-danger-soft text-danger border-danger/30",
  amber: "bg-amber-soft text-amber border-amber/30",
  outline: "bg-white text-ink border-line-strong",
};

export function Badge({
  tone = "neutral",
  children,
  className,
  dot,
}: {
  tone?: Tone;
  children: React.ReactNode;
  className?: string;
  dot?: boolean;
}) {
  return (
    <span
      className={cn(
        "inline-flex h-[22px] items-center gap-1.5 whitespace-nowrap rounded-xs border px-2 font-mono text-[11px] font-medium leading-none",
        tones[tone],
        className,
      )}
    >
      {dot && <span className="h-1.5 w-1.5 rounded-full bg-current" />}
      {children}
    </span>
  );
}

export function StatusDot({ ok, pulse, className }: { ok: boolean | null; pulse?: boolean; className?: string }) {
  return (
    <span
      className={cn(
        "inline-block h-2 w-2 rounded-full",
        ok === null ? "bg-line-strong" : ok ? "bg-lime ring-1 ring-ink" : "bg-danger",
        pulse && "animate-pulse-dot",
        className,
      )}
    />
  );
}
