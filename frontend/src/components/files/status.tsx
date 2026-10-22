import { Badge } from "@/components/ui/badge";
import type { AccessLevel, IndexStatus } from "@/lib/types";

export function IndexBadge({ status }: { status: IndexStatus }) {
  if (status === "ready") return <Badge tone="outline" dot className="[&>span]:bg-lime [&>span]:ring-1 [&>span]:ring-ink">Ready</Badge>;
  if (status === "failed") return <Badge tone="danger" dot>Failed</Badge>;
  return (
    <Badge tone="amber" dot className="[&>span]:animate-pulse-dot">
      {status === "processing" ? "Indexing" : "Queued"}
    </Badge>
  );
}

const ACCESS: Record<AccessLevel, string> = {
  public: "Company",
  department: "Department",
  private: "Private",
};

export function AccessBadge({ level }: { level: AccessLevel | null }) {
  if (!level) return null;
  return <Badge tone={level === "public" ? "ink" : level === "private" ? "neutral" : "outline"}>{ACCESS[level]}</Badge>;
}

export const accessLabel = (l: AccessLevel) => ACCESS[l];
