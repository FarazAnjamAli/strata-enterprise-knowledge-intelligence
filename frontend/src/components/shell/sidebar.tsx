"use client";

import { BookOpen, KeyRound, LayoutGrid, LogOut, MessageSquare, Settings, ShieldCheck } from "lucide-react";
import { motion } from "motion/react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Logo } from "@/components/brand";
import { cn } from "@/lib/cn";
import { initials } from "@/lib/format";
import { useSession } from "@/lib/session";
import { TierStackMini } from "./tier-stack";

const NAV = [
  { href: "/overview", label: "Overview", icon: LayoutGrid },
  { href: "/chat", label: "Assistant", icon: MessageSquare },
  { href: "/library", label: "Library", icon: BookOpen },
  { href: "/access", label: "Access", icon: KeyRound },
];

function NavItem({ href, label, icon: Icon }: { href: string; label: string; icon: typeof LayoutGrid }) {
  const path = usePathname();
  const active = path === href || path.startsWith(`${href}/`);
  return (
    <Link
      href={href}
      className={cn(
        "group relative flex h-9 items-center gap-3 rounded-xs px-3 text-sm transition-colors",
        active ? "font-medium text-ink" : "text-ink-2 hover:bg-paper hover:text-ink",
      )}
    >
      {active && (
        <motion.span
          layoutId="nav-active"
          className="absolute inset-0 rounded-xs bg-wash"
          transition={{ type: "spring", stiffness: 420, damping: 36 }}
        >
          <span className="absolute inset-y-1.5 left-0 w-[3px] bg-lime ring-1 ring-ink" />
        </motion.span>
      )}
      <Icon className="relative h-[17px] w-[17px] transition-transform duration-200 group-hover:-translate-y-px" strokeWidth={1.5} />
      <span className="relative">{label}</span>
    </Link>
  );
}

export function Sidebar() {
  const { profile, status, isAdmin, signOut } = useSession();
  return (
    <aside className="flex w-[244px] shrink-0 flex-col border-r border-line bg-white">
      <div className="flex h-16 items-center px-5">
        <Link href="/overview" aria-label="Strata home">
          <Logo size="sm" animated />
        </Link>
      </div>

      <nav className="space-y-0.5 px-3 pt-2">
        <p className="px-3 pb-2 font-mono text-2xs uppercase text-ink-3">Workspace</p>
        {NAV.map((n) => (
          <NavItem key={n.href} {...n} />
        ))}
        {isAdmin && (
          <>
            <p className="px-3 pb-2 pt-5 font-mono text-2xs uppercase text-ink-3">Administration</p>
            <NavItem href="/admin" label="Admin console" icon={ShieldCheck} />
          </>
        )}
      </nav>

      <div className="mt-auto space-y-4 p-4">
        <div className="rounded-sm border border-line p-3.5">
          <div className="mb-3 flex items-center justify-between">
            <p className="font-mono text-2xs uppercase text-ink-2">Model tiers</p>
            <span className="font-mono text-[10px] text-ink-3">routing ↓</span>
          </div>
          <TierStackMini tiers={status?.tiers} />
        </div>

        <div className="flex items-center gap-3 border-t border-line pt-4">
          <div className="grid h-8 w-8 shrink-0 place-items-center rounded-xs bg-ink font-mono text-[11px] font-medium text-lime">
            {initials(profile?.full_name, profile?.email)}
          </div>
          <div className="min-w-0 flex-1">
            <p className="truncate text-[13px] font-medium text-ink">{profile?.full_name || profile?.email || "…"}</p>
            <p className="truncate text-xs text-ink-2">{profile ? `${profile.role}${profile.department ? ` · ${profile.department}` : ""}` : ""}</p>
          </div>
          <Link href="/settings" className="grid h-7 w-7 place-items-center rounded-xs text-ink-2 hover:bg-wash hover:text-ink" aria-label="Settings">
            <Settings className="h-4 w-4" strokeWidth={1.5} />
          </Link>
          <button onClick={() => void signOut()} className="grid h-7 w-7 place-items-center rounded-xs text-ink-2 hover:bg-wash hover:text-ink" aria-label="Sign out" title="Sign out">
            <LogOut className="h-4 w-4" strokeWidth={1.5} />
          </button>
        </div>
      </div>
    </aside>
  );
}
