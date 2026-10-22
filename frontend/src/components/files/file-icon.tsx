import { cn } from "@/lib/cn";
import { ext } from "@/lib/format";

const COLORS: Record<string, string> = {
  pdf: "bg-ink text-white",
  docx: "bg-white text-ink",
  xlsx: "bg-lime text-ink",
  csv: "bg-lime text-ink",
};

export function FileIcon({ name, className }: { name: string; className?: string }) {
  const e = ext(name) || "file";
  return (
    <span
      className={cn(
        "grid h-8 w-8 shrink-0 place-items-center rounded-xs border border-ink font-mono text-[9px] font-medium uppercase leading-none",
        COLORS[e] ?? "bg-paper text-ink",
        className,
      )}
    >
      {e.slice(0, 4)}
    </span>
  );
}
