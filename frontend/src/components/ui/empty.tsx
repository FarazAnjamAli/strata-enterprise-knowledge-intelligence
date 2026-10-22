import { cn } from "@/lib/cn";

export function Empty({
  icon,
  title,
  children,
  action,
  className,
}: {
  icon?: React.ReactNode;
  title: string;
  children?: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col items-center justify-center px-6 py-14 text-center", className)}>
      {icon && (
        <div className="mb-4 grid h-11 w-11 place-items-center rounded-sm border border-line bg-paper text-ink">{icon}</div>
      )}
      <p className="text-[15px] font-medium text-ink">{title}</p>
      {children && <p className="mt-1.5 max-w-sm text-sm leading-relaxed text-ink-2">{children}</p>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("relative overflow-hidden rounded-xs bg-wash", className)}>
    <div className="absolute inset-0 animate-scan bg-gradient-to-r from-transparent via-white/70 to-transparent" />
  </div>;
}
