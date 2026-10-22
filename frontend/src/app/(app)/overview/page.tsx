"use client";

import { ArrowRight, ArrowUpRight, CornerDownLeft, FileText, MessageSquare, Upload } from "lucide-react";
import { motion } from "motion/react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import useSWR from "swr";
import { FileIcon } from "@/components/files/file-icon";
import { AccessBadge, IndexBadge } from "@/components/files/status";
import { CountUp, Reveal, Stagger, StaggerItem } from "@/components/motion";
import { sortTiers, tierTone } from "@/components/shell/tier-stack";
import { Button } from "@/components/ui/button";
import { Empty, Skeleton } from "@/components/ui/empty";
import { Panel } from "@/components/ui/panel";
import { openFile } from "@/lib/api";
import { cn } from "@/lib/cn";
import { type Conversation, loadConversations } from "@/lib/conversations";
import { ago, num, usd } from "@/lib/format";
import { useSession } from "@/lib/session";
import type { ActivityPoint, FileOut, TeamStats, TierStatus } from "@/lib/types";

function greeting() {
  const h = new Date().getHours();
  return h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening";
}

const PROMPTS = [
  "Summarize our travel and expense policy",
  "Who approves new vendors?",
  "What changed in the latest security policy?",
];

// ----------------------------------------------------------------- hero

function today() {
  return new Date().toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long" });
}

function Hero({ first, role, department }: { first?: string; role?: string | null; department?: string | null }) {
  const router = useRouter();
  const [q, setQ] = useState("");
  const go = (text: string) => text.trim() && router.push(`/chat?q=${encodeURIComponent(text.trim())}`);

  return (
    <section className="border-b border-line pb-10">
      <div className="flex flex-wrap items-start justify-between gap-6">
        <div>
          <motion.p
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.4 }}
            className="font-mono text-[11px] uppercase tracking-[0.08em] text-ink-2"
          >
            {today()}
            {department && <span className="text-ink-3"> / {department}</span>}
          </motion.p>
          <motion.h1
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.55, ease: [0.2, 0.7, 0.2, 1] }}
            className="mt-3 text-[52px] font-semibold leading-[1] tracking-[-0.02em] text-ink"
          >
            {greeting()}
            {first ? `, ${first}` : ""}
          </motion.h1>
          {role && (
            <motion.p
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.2, duration: 0.4 }}
              className="mt-3 text-[15px] text-ink-2"
            >
              Signed in as <span className="font-medium text-ink">{role}</span>
            </motion.p>
          )}
        </div>
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.15 }}
          className="flex gap-2 pt-1"
        >
          <Link href="/library">
            <Button variant="secondary">
              <Upload className="h-4 w-4" strokeWidth={1.5} /> Upload
            </Button>
          </Link>
          <Link href="/chat">
            <Button variant="primary">
              New chat <ArrowRight className="h-4 w-4" strokeWidth={1.75} />
            </Button>
          </Link>
        </motion.div>
      </div>

      <motion.form
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.15, duration: 0.5, ease: [0.2, 0.7, 0.2, 1] }}
        onSubmit={(e) => {
          e.preventDefault();
          go(q);
        }}
        className="mt-9 flex items-center rounded-sm border border-line-strong bg-white transition-colors focus-within:border-ink"
      >
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Ask anything about your documents"
          aria-label="Ask a question"
          className="h-14 flex-1 bg-transparent px-5 text-[16px] text-ink placeholder:text-ink-3 focus:outline-none"
        />
        <button
          type="submit"
          className="m-1.5 flex h-11 items-center gap-2 rounded-xs bg-ink px-5 text-sm font-medium text-white transition-colors hover:bg-ink-2"
        >
          Ask <CornerDownLeft className="h-3.5 w-3.5" strokeWidth={1.75} />
        </button>
      </motion.form>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <span className="mr-1 font-mono text-[11px] uppercase text-ink-3">Try</span>
        {PROMPTS.map((p, i) => (
          <motion.button
            key={p}
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.3 + i * 0.06 }}
            onClick={() => go(p)}
            className="rounded-xs border border-line px-3 py-1.5 text-[13px] text-ink-2 transition-colors hover:border-ink hover:text-ink"
          >
            {p}
          </motion.button>
        ))}
      </div>
    </section>
  );
}

// ------------------------------------------------------------- pipeline

function Pipeline({ tiers }: { tiers: TierStatus[] }) {
  const activeIdx = tiers.findIndex((t) => tierTone(t) === "ok");
  return (
    <div className="relative">
      {/* the rail a question travels down until a tier answers */}
      <div className="absolute bottom-6 left-[27px] top-6 w-px bg-line-strong" />
      {tiers.map((t, i) => {
        const tone = tierTone(t);
        const budget = t.tier === "paid" && t.monthly_budget_usd ? t.monthly_budget_usd : null;
        const spend = t.month_spend_usd ?? 0;
        return (
          <Reveal key={t.tier} delay={0.08 * i}>
            <div className="relative flex items-center gap-5 py-4 pl-3 pr-1">
              <span
                className={cn(
                  "relative z-10 grid h-8 w-8 shrink-0 place-items-center rounded-xs border font-mono text-[11px]",
                  i === activeIdx ? "border-ink bg-lime text-ink" : tone === "down" ? "border-danger bg-white text-danger" : "border-line-strong bg-white text-ink-2",
                )}
              >
                0{i + 1}
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <p className={cn("text-[15px] font-medium", tone === "off" ? "text-ink-3" : "text-ink")}>{t.tier_label}</p>
                  {i === activeIdx && (
                    <span className="rounded-xs bg-ink px-1.5 py-0.5 font-mono text-[10px] uppercase text-lime">answering</span>
                  )}
                  {t.tier === "paid" && t.requires_confirmation && tone !== "off" && (
                    <span className="rounded-xs border border-line-strong px-1.5 py-0.5 font-mono text-[10px] uppercase text-ink-2">asks first</span>
                  )}
                </div>
                <p className="truncate font-mono text-xs text-ink-2">
                  {t.provider} · {t.model}
                </p>
                {budget !== null && tone !== "off" && (
                  <div className="mt-2 flex items-center gap-3">
                    <div className="h-1 w-28 shrink-0 bg-wash">
                      <motion.div
                        className="h-full bg-ink"
                        initial={{ width: 0 }}
                        whileInView={{ width: `${Math.min(100, (spend / budget) * 100)}%` }}
                        viewport={{ once: true }}
                        transition={{ duration: 0.9 }}
                      />
                    </div>
                    <span className="whitespace-nowrap font-mono text-[11px] text-ink-2">
                      {usd(spend)} / {usd(budget)} this month
                    </span>
                  </div>
                )}
              </div>
              <span
                className={cn(
                  "flex items-center gap-1.5 font-mono text-[11px] uppercase",
                  tone === "ok" ? "text-ink" : tone === "down" ? "text-danger" : "text-ink-3",
                )}
              >
                <span
                  className={cn(
                    "h-1.5 w-1.5 rounded-full",
                    tone === "ok" ? "bg-lime ring-1 ring-ink" : tone === "down" ? "bg-danger" : "border border-line-strong",
                  )}
                />
                {tone === "ok" ? "operational" : tone === "down" ? "unreachable" : "disabled"}
              </span>
            </div>
          </Reveal>
        );
      })}
    </div>
  );
}

// ----------------------------------------------------------------- spark

function Spark({ points }: { points: ActivityPoint[] }) {
  const max = Math.max(1, ...points.map((p) => p.queries));
  return (
    <div className="flex h-28 items-end gap-[4px]">
      {points.map((p, i) => (
        <div key={p.day} className="group relative flex h-full flex-1 items-end" title={`${p.day}: ${p.queries} questions, ${p.uploads} uploads`}>
          <motion.div
            className="w-full origin-bottom bg-ink transition-colors group-hover:bg-lime group-hover:ring-1 group-hover:ring-ink"
            style={{ height: `${Math.max(3, (p.queries / max) * 100)}%` }}
            initial={{ scaleY: 0 }}
            whileInView={{ scaleY: 1 }}
            viewport={{ once: true }}
            transition={{ duration: 0.6, delay: i * 0.035, ease: [0.2, 0.7, 0.2, 1] }}
          />
          <span className="pointer-events-none absolute -top-6 left-1/2 -translate-x-1/2 whitespace-nowrap rounded-xs bg-ink px-1.5 py-0.5 font-mono text-[10px] text-lime opacity-0 transition-opacity group-hover:opacity-100">
            {p.queries}
          </span>
        </div>
      ))}
    </div>
  );
}

// ------------------------------------------------------------------ stat

function StatCard({ label, value, hint, accent, index }: { label: string; value: number | string | null; hint: string; accent?: boolean; index: number }) {
  return (
    <StaggerItem className={cn("group relative overflow-hidden p-6", accent ? "bg-ink" : "bg-white")}>
      <div className="relative flex items-center justify-between">
        <p className={cn("font-mono text-2xs uppercase", accent ? "text-lime" : "text-ink-2")}>{label}</p>
        <span className={cn("font-mono text-[10px]", accent ? "text-white/60" : "text-ink-3")}>0{index + 1}</span>
      </div>
      <p className={cn("relative mt-5 text-[38px] font-medium leading-none tracking-[-0.02em]", accent ? "text-white" : "text-ink")}>
        {value === null ? "–" : typeof value === "number" ? <CountUp value={value} /> : value}
      </p>
      <p className={cn("relative mt-2.5 truncate text-xs", accent ? "text-white/80" : "text-ink-2")}>{hint}</p>
      {!accent && <span className="absolute bottom-0 left-0 h-[2px] w-0 bg-lime transition-all duration-500 group-hover:w-full" />}
    </StaggerItem>
  );
}

// ------------------------------------------------------------------ page

export default function OverviewPage() {
  const { profile, status, isAdmin, isHead } = useSession();
  const { data: files } = useSWR<FileOut[]>("/api/files?limit=500");
  const { data: team } = useSWR<TeamStats>(isHead && profile?.department ? "/api/team/stats" : null);
  const { data: activity } = useSWR<ActivityPoint[]>(isAdmin ? "/api/admin/activity?days=14" : null);
  const [convs, setConvs] = useState<Conversation[]>([]);
  useEffect(() => {
    if (profile) setConvs(loadConversations(profile.id));
  }, [profile]);

  const ready = useMemo(() => files?.filter((f) => f.index_status === "ready") ?? [], [files]);
  const working = files?.filter((f) => f.index_status === "pending" || f.index_status === "processing").length ?? 0;
  const tiers = sortTiers(status?.tiers);
  const active = tiers.find((t) => tierTone(t) === "ok");

  return (
    <div className="mx-auto w-full max-w-[1200px] px-10 py-10">
      <Hero first={profile?.full_name?.split(" ")[0]} role={profile?.role} department={profile?.department} />

      <Stagger className="mt-10 grid grid-cols-2 divide-x divide-line overflow-hidden rounded-sm border border-line lg:grid-cols-4">
        <StatCard index={0} label="Documents" value={files ? ready.length : null} hint={`${working} indexing right now`} />
        <StatCard index={1} label="Passages" value={files ? ready.reduce((a, f) => a + (f.chunk_count || 0), 0) : null} hint="searchable chunks" />
        <StatCard index={2} label="Conversations" value={convs.length} hint="saved on this device" />
        <StatCard index={3} accent label="Answering now" value={active ? active.tier_label : status ? "None" : null} hint={active ? `${active.provider} · ${active.model}` : "no tier reachable"} />
      </Stagger>

      <div className="mt-6 grid gap-6 lg:grid-cols-[1.25fr_1fr]">
        <Reveal>
          <Panel eyebrow="Routing" title="Model tiers" action={<span className="font-mono text-[11px] text-ink-3">tried top → bottom</span>} bodyClassName="py-2 px-3">
            {tiers.length ? <Pipeline tiers={tiers} /> : <Skeleton className="my-4 h-40" />}
          </Panel>
        </Reveal>

        <Reveal delay={0.08}>
          <Panel
            eyebrow="Continue"
            title="Recent conversations"
            className="h-full"
            action={<Link href="/chat" className="text-[13px] text-ink-2 transition-colors hover:text-ink">Open assistant →</Link>}
            bodyClassName="p-0"
          >
            {convs.length === 0 ? (
              <Empty icon={<MessageSquare className="h-5 w-5" strokeWidth={1.5} />} title="No conversations yet" className="py-12">
                Questions you ask the assistant appear here.
              </Empty>
            ) : (
              <Stagger as="ul">
                {convs.slice(0, 6).map((c) => (
                  <StaggerItem as="li" key={c.id}>
                    <Link href={`/chat?c=${c.id}`} className="group flex items-center gap-3 border-b border-line px-5 py-3.5 transition-colors last:border-b-0 hover:bg-paper">
                      <span className="h-1.5 w-1.5 shrink-0 bg-ink transition-all group-hover:w-3 group-hover:bg-lime group-hover:ring-1 group-hover:ring-ink" />
                      <span className="flex-1 truncate text-sm text-ink">{c.title}</span>
                      <span className="font-mono text-[11px] text-ink-3">{ago(new Date(c.updated).toISOString())}</span>
                    </Link>
                  </StaggerItem>
                ))}
              </Stagger>
            )}
          </Panel>
        </Reveal>
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-[1.25fr_1fr]">
        <Reveal>
          <Panel
            eyebrow="Library"
            title="Recently added"
            action={<Link href="/library" className="text-[13px] text-ink-2 transition-colors hover:text-ink">View all →</Link>}
            bodyClassName="p-0"
          >
            {!files ? (
              <div className="space-y-2 p-5">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-10" />)}</div>
            ) : files.length === 0 ? (
              <Empty
                icon={<FileText className="h-5 w-5" strokeWidth={1.5} />}
                title="No documents yet"
                action={<Link href="/library"><Button variant="accent" size="sm">Upload your first file</Button></Link>}
              >
                Upload PDFs, Word, Excel, CSV, Markdown or images. They&apos;re indexed automatically.
              </Empty>
            ) : (
              <Stagger as="ul">
                {files.slice(0, 6).map((f) => (
                  <StaggerItem as="li" key={f.id} className="group flex items-center gap-3 border-b border-line px-5 py-3 transition-colors last:border-b-0 hover:bg-paper">
                    <FileIcon name={f.name} className="transition-transform group-hover:-rotate-3" />
                    <button onClick={() => void openFile(f.id)} className="min-w-0 flex-1 text-left">
                      <p className="truncate text-sm font-medium text-ink group-hover:underline">{f.name}</p>
                      <p className="text-xs text-ink-2">{f.department ?? "Personal"} · {ago(f.created_at)}</p>
                    </button>
                    <AccessBadge level={f.access_level} />
                    <IndexBadge status={f.index_status} />
                  </StaggerItem>
                ))}
              </Stagger>
            )}
          </Panel>
        </Reveal>

        <Reveal delay={0.08}>
          {isAdmin && activity ? (
            <Panel
              eyebrow="Usage"
              title="Questions asked · 14 days"
              className="h-full"
              action={<Link href="/admin" className="text-[13px] text-ink-2 hover:text-ink">Console <ArrowUpRight className="inline h-3.5 w-3.5" /></Link>}
            >
              <p className="mb-6 text-[34px] font-medium leading-none tracking-[-0.02em] text-ink">
                <CountUp value={activity.reduce((a, p) => a + p.queries, 0)} />
                <span className="ml-2 font-mono text-xs tracking-normal text-ink-2">questions</span>
              </p>
              <Spark points={activity} />
              <div className="mt-3 flex justify-between font-mono text-[11px] text-ink-3">
                <span>{activity[0]?.day}</span>
                <span>{activity[activity.length - 1]?.day}</span>
              </div>
            </Panel>
          ) : team ? (
            <Panel eyebrow={team.department} title="Your team · 7 days" className="h-full" bodyClassName="p-0">
              <div className="grid grid-cols-3 divide-x divide-line border-b border-line">
                {[["Active", `${team.members_active_7d}/${team.members_total}`], ["Questions", num(team.queries_7d)], ["Uploads", num(team.uploads_7d)]].map(([k, v]) => (
                  <div key={k} className="p-5">
                    <p className="font-mono text-2xs uppercase text-ink-2">{k}</p>
                    <p className="mt-2 text-2xl font-medium tracking-[-0.02em]">{v}</p>
                  </div>
                ))}
              </div>
              <ul>
                {team.members.slice(0, 5).map((m) => (
                  <li key={m.id} className="flex items-center justify-between border-b border-line px-5 py-2.5 text-sm last:border-b-0">
                    <span className="truncate text-ink">{m.name}</span>
                    <span className="font-mono text-xs text-ink-2">{m.queries_7d} q · {ago(m.last_login)}</span>
                  </li>
                ))}
              </ul>
            </Panel>
          ) : (
            <Panel eyebrow="Tips" title="Getting better answers" className="h-full">
              <ul className="space-y-3 text-sm text-ink-2">
                <li><span className="font-mono text-ink">/file</span> asks one document in isolation.</li>
                <li>Name the document in your question to search only that file.</li>
                <li>Every answer cites its sources. Click one to open it.</li>
                <li>Need another team&apos;s file? Request it under <Link className="text-ink underline decoration-lime decoration-2" href="/access">Access</Link>.</li>
              </ul>
            </Panel>
          )}
        </Reveal>
      </div>

      <Reveal className="mt-10 flex items-center justify-between border-t border-line pt-5 font-mono text-[11px] text-ink-3">
        <span>Strata · on-prem first</span>
        <span>{tiers.filter((t) => tierTone(t) === "ok").length}/3 tiers operational</span>
      </Reveal>
    </div>
  );
}
