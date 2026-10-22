"use client";

import { Download, KeyRound, Plus, Search, UserPlus } from "lucide-react";
import { motion } from "motion/react";
import { useMemo, useState } from "react";
import { CountUp, Reveal } from "@/components/motion";
import useSWR from "swr";
import { sortTiers, tierTone } from "@/components/shell/tier-stack";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Empty, Skeleton } from "@/components/ui/empty";
import { Field, Input, Select } from "@/components/ui/field";
import { PageHeader, Panel, Stat } from "@/components/ui/panel";
import { Segmented, Tabs } from "@/components/ui/tabs";
import { Table, Td, Th, Tr } from "@/components/ui/table";
import { useToast } from "@/components/ui/toast";
import { ApiError, downloadUrl, patch, post } from "@/lib/api";
import { cn } from "@/lib/cn";
import { ago, dateTime, initials, num, usd } from "@/lib/format";
import { useSession } from "@/lib/session";
import type { AuditLogOut, LLMUsageReport, Meta, Stats, UserOut } from "@/lib/types";

type Tab = "users" | "models" | "audit" | "system";

export default function AdminPage() {
  const { isAdmin, profile } = useSession();
  const [tab, setTab] = useState<Tab>("users");
  if (profile && !isAdmin)
    return (
      <div className="p-10">
        <Empty title="Admins only">You don&apos;t have access to the admin console.</Empty>
      </div>
    );
  return (
    <div className="mx-auto w-full max-w-[1280px] px-10 py-10">
      <PageHeader
        eyebrow="Administration"
        title="Admin console"
        description="People and roles, model routing and spend, and the full audit trail."
      />
      <Tabs
        value={tab}
        onChange={setTab}
        items={[
          { value: "users", label: "People" },
          { value: "models", label: "Models & cost" },
          { value: "audit", label: "Audit log" },
          { value: "system", label: "System" },
        ]}
      />
      <div className="mt-6">
        {tab === "users" && <UsersTab />}
        {tab === "models" && <ModelsTab />}
        {tab === "audit" && <AuditTab />}
        {tab === "system" && <SystemTab />}
      </div>
    </div>
  );
}

// ------------------------------------------------------------------- users

function UsersTab() {
  const toast = useToast();
  const { status, profile } = useSession();
  const { data: meta } = useSWR<Meta>("/api/system/meta");
  const { data: users, mutate } = useSWR<UserOut[]>("/api/admin/users");
  const [q, setQ] = useState("");
  const [adding, setAdding] = useState(false);
  const [resetFor, setResetFor] = useState<UserOut | null>(null);
  const local = meta?.auth_provider === "local";

  const shown = useMemo(
    () =>
      (users ?? []).filter((u) =>
        [u.email, u.full_name, u.department, u.role].some((v) => (v ?? "").toLowerCase().includes(q.toLowerCase())),
      ),
    [users, q],
  );

  async function update(u: UserOut, body: Partial<UserOut>) {
    try {
      await patch(`/api/admin/users/${u.id}`, body);
      toast("ok", `Updated ${u.full_name || u.email}`);
      void mutate();
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : "Update failed");
    }
  }

  return (
    <>
      <div className="mb-4 flex items-center justify-between gap-3">
        <div className="relative w-80">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-2" strokeWidth={1.5} />
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search people" className="pl-9" />
        </div>
        <Button variant="primary" onClick={() => setAdding(true)}>
          <UserPlus className="h-4 w-4" strokeWidth={1.5} /> Add person
        </Button>
      </div>
      <datalist id="departments">
        {status?.departments.map((d) => <option key={d} value={d} />)}
      </datalist>
      <div className="rounded-sm border border-line">
        {!users ? (
          <div className="space-y-2 p-4">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-11" />)}</div>
        ) : (
          <Table>
            <thead>
              <tr>
                <Th>Person</Th>
                <Th>Role</Th>
                <Th>Department</Th>
                <Th>Status</Th>
                <Th>Last active</Th>
                <Th className="w-12" />
              </tr>
            </thead>
            <tbody>
              {shown.map((u) => (
                <Tr key={u.id}>
                  <Td>
                    <div className="flex items-center gap-3">
                      <span className={cn("grid h-8 w-8 shrink-0 place-items-center rounded-xs font-mono text-[11px]", u.role === "Admin" ? "bg-ink text-lime" : "bg-wash text-ink")}>
                        {initials(u.full_name, u.email)}
                      </span>
                      <div className="min-w-0">
                        <p className="truncate font-medium text-ink">{u.full_name || "-"}</p>
                        <p className="truncate text-xs text-ink-2">{u.email}</p>
                      </div>
                    </div>
                  </Td>
                  <Td>
                    <Select
                      value={u.role ?? "Member"}
                      onChange={(e) => void update(u, { role: e.target.value as UserOut["role"] })}
                      className="h-8 w-[160px] text-[13px]"
                      disabled={u.id === profile?.id}
                      aria-label="Role"
                    >
                      {status?.roles.map((r) => <option key={r}>{r}</option>)}
                    </Select>
                  </Td>
                  <Td>
                    <Input
                      defaultValue={u.department ?? ""}
                      list="departments"
                      placeholder="Unassigned"
                      className="h-8 w-[180px] text-[13px]"
                      onBlur={(e) => e.target.value !== (u.department ?? "") && void update(u, { department: e.target.value })}
                      onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()}
                      aria-label="Department"
                    />
                  </Td>
                  <Td>
                    <button
                      disabled={u.id === profile?.id}
                      onClick={() => void update(u, { is_active: !u.is_active })}
                      className="disabled:cursor-not-allowed"
                      title={u.is_active ? "Click to disable" : "Click to enable"}
                    >
                      {u.is_active ? <Badge tone="outline" dot className="[&>span]:bg-lime [&>span]:ring-1 [&>span]:ring-ink">Active</Badge> : <Badge tone="danger">Disabled</Badge>}
                    </button>
                  </Td>
                  <Td className="whitespace-nowrap text-ink-2">{ago(u.last_login)}</Td>
                  <Td>
                    {local && (
                      <Button size="icon" variant="ghost" onClick={() => setResetFor(u)} aria-label="Reset password" title="Reset password">
                        <KeyRound className="h-4 w-4" strokeWidth={1.5} />
                      </Button>
                    )}
                  </Td>
                </Tr>
              ))}
            </tbody>
          </Table>
        )}
      </div>
      <AddUserDialog open={adding} local={local} onClose={() => setAdding(false)} onDone={() => { setAdding(false); void mutate(); }} />
      <ResetDialog user={resetFor} onClose={() => setResetFor(null)} />
    </>
  );
}

function AddUserDialog({ open, local, onClose, onDone }: { open: boolean; local: boolean; onClose: () => void; onDone: () => void }) {
  const toast = useToast();
  const { status } = useSession();
  const [form, setForm] = useState({ email: "", full_name: "", password: "", role: "Member", department: "" });
  const [err, setErr] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm((f) => ({ ...f, [k]: e.target.value }));

  async function save() {
    setSaving(true);
    setErr(null);
    try {
      await post("/api/admin/users", { ...form, password: local ? form.password : null });
      toast("ok", `Added ${form.email}`);
      setForm({ email: "", full_name: "", password: "", role: "Member", department: "" });
      onDone();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Couldn't add person");
    } finally {
      setSaving(false);
    }
  }
  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Add a person"
      description={local ? "They can sign in immediately with this password." : "Role and department apply on their first sign-in."}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button variant="primary" loading={saving} onClick={() => void save()}>
            <Plus className="h-4 w-4" /> Add person
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        {err && <p className="rounded-sm border border-danger/40 bg-danger-soft px-3 py-2 text-sm text-danger">{err}</p>}
        <div className="grid grid-cols-2 gap-4">
          <Field label="Full name"><Input value={form.full_name} onChange={set("full_name")} placeholder="Ada Lovelace" /></Field>
          <Field label="Email"><Input type="email" value={form.email} onChange={set("email")} placeholder="ada@company.com" /></Field>
        </div>
        <div className="grid grid-cols-2 gap-4">
          <Field label="Role">
            <Select value={form.role} onChange={set("role")}>{status?.roles.map((r) => <option key={r}>{r}</option>)}</Select>
          </Field>
          <Field label="Department"><Input value={form.department} onChange={set("department")} list="departments" placeholder="Unassigned" /></Field>
        </div>
        {local && (
          <Field label="Initial password" hint="12+ characters, mixing upper, lower, digits or symbols.">
            <Input type="text" value={form.password} onChange={set("password")} autoComplete="new-password" />
          </Field>
        )}
      </div>
    </Dialog>
  );
}

function ResetDialog({ user, onClose }: { user: UserOut | null; onClose: () => void }) {
  const toast = useToast();
  const [pw, setPw] = useState("");
  const [err, setErr] = useState<string | null>(null);
  return (
    <Dialog
      open={!!user}
      onClose={onClose}
      title="Reset password"
      description={user ? `For ${user.email}. Their other sessions are signed out.` : ""}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button
            variant="primary"
            onClick={async () => {
              try {
                await post(`/api/admin/users/${user!.id}/password`, { password: pw });
                toast("ok", "Password reset");
                setPw("");
                setErr(null);
                onClose();
              } catch (e) {
                setErr(e instanceof ApiError ? e.message : "Reset failed");
              }
            }}
          >
            Reset
          </Button>
        </>
      }
    >
      <Field label="New password" error={err}>
        <Input value={pw} onChange={(e) => setPw(e.target.value)} autoComplete="new-password" />
      </Field>
    </Dialog>
  );
}

// ------------------------------------------------------------------ models

const TIER_COLORS = { local: "bg-lime ring-1 ring-inset ring-ink", free: "bg-ink", paid: "bg-amber" } as const;

function ModelsTab() {
  const { status } = useSession();
  const [days, setDays] = useState<"7" | "30" | "90">("30");
  const { data } = useSWR<LLMUsageReport>(`/api/admin/llm-usage?days=${days}`);
  const tiers = sortTiers(status?.tiers);
  const max = Math.max(1, ...(data?.daily.map((d) => d.local + d.free + d.paid) ?? [1]));
  const total = data?.tiers.reduce((a, t) => a + t.calls - t.failures, 0) ?? 0;

  return (
    <div className="space-y-6">
      <div className="grid gap-4 lg:grid-cols-3">
        {tiers.map((t, i) => {
          const u = data?.tiers.find((x) => x.tier === t.tier);
          const tone = tierTone(t);
          return (
            <Reveal key={t.tier} delay={i * 0.08} className={cn("lift relative overflow-hidden rounded-sm border bg-white p-5", tone === "ok" ? "border-ink" : "border-line")}>
              <div className="flex items-center justify-between">
                <span className="font-mono text-xs text-ink-3">0{i + 1}</span>
                <span className={cn("font-mono text-[11px] uppercase", tone === "ok" ? "text-ink" : tone === "down" ? "text-danger" : "text-ink-3")}>
                  {tone === "ok" ? "● operational" : tone === "down" ? "● unreachable" : "○ disabled"}
                </span>
              </div>
              <div className="mt-4 flex items-center gap-3">
                <span className={cn("h-3 w-9 -skew-x-[30deg]", TIER_COLORS[t.tier])} />
                <p className="text-lg font-medium tracking-[-0.02em] text-ink">{t.tier_label}</p>
              </div>
              <p className="mt-1 font-mono text-xs text-ink-2">{t.provider} · {t.model}</p>
              <dl className="mt-5 grid grid-cols-3 gap-3 border-t border-line pt-4">
                <div>
                  <dt className="font-mono text-2xs uppercase text-ink-2">Answers</dt>
                  <dd className="mt-1 text-lg font-medium tabular-nums"><CountUp value={(u?.calls ?? 0) - (u?.failures ?? 0)} /></dd>
                </div>
                <div>
                  <dt className="font-mono text-2xs uppercase text-ink-2">Failures</dt>
                  <dd className={cn("mt-1 text-lg font-medium tabular-nums", (u?.failures ?? 0) > 0 && "text-danger")}>{num(u?.failures ?? 0)}</dd>
                </div>
                <div>
                  <dt className="font-mono text-2xs uppercase text-ink-2">{t.tier === "paid" ? "Cost" : "Latency"}</dt>
                  <dd className="mt-1 text-lg font-medium tabular-nums">
                    {t.tier === "paid" ? usd(u?.cost_usd ?? 0) : u?.avg_latency_ms ? `${(u.avg_latency_ms / 1000).toFixed(1)}s` : "-"}
                  </dd>
                </div>
              </dl>
            </Reveal>
          );
        })}
      </div>

      <Panel
        eyebrow="Routing history"
        title="Which tier answered"
        action={<Segmented size="sm" value={days} onChange={setDays} items={[{ value: "7", label: "7d" }, { value: "30", label: "30d" }, { value: "90", label: "90d" }]} />}
      >
        {!data ? (
          <Skeleton className="h-48" />
        ) : total === 0 ? (
          <Empty title="No answers yet" className="py-10">Usage appears here once people start asking questions.</Empty>
        ) : (
          <>
            <div className="flex h-48 items-end gap-[3px] border-b border-line">
              {data.daily.map((d) => {
                const sum = d.local + d.free + d.paid;
                return (
                  <div key={d.day} className="flex flex-1 flex-col justify-end" title={`${d.day}: local ${d.local}, free ${d.free}, premium ${d.paid}`}>
                    {(["paid", "free", "local"] as const).map((k) =>
                      d[k] ? (
                        <motion.div
                          key={k}
                          className={cn("origin-bottom", TIER_COLORS[k])}
                          style={{ height: `${(d[k] / max) * 184}px` }}
                          initial={{ scaleY: 0 }}
                          animate={{ scaleY: 1 }}
                          transition={{ duration: 0.7, ease: [0.2, 0.7, 0.2, 1] }}
                        />
                      ) : null,
                    )}
                    {sum === 0 && <div className="h-px bg-line" />}
                  </div>
                );
              })}
            </div>
            <div className="mt-3 flex items-center justify-between">
              <div className="flex gap-5">
                {(["local", "free", "paid"] as const).map((k) => (
                  <span key={k} className="flex items-center gap-2 text-xs text-ink-2">
                    <span className={cn("h-2.5 w-2.5", TIER_COLORS[k])} />
                    {k === "local" ? "Local model" : k === "free" ? "Free API" : "Premium API"}
                  </span>
                ))}
              </div>
              <span className="font-mono text-xs text-ink-2">
                Premium spend this month: <span className="text-ink">{usd(data.month_paid_spend_usd)}</span> of {usd(data.monthly_budget_usd)}
              </span>
            </div>
          </>
        )}
      </Panel>

      <Panel eyebrow="Detail" title="Token usage" bodyClassName="p-0">
        <Table>
          <thead>
            <tr>
              <Th>Tier</Th>
              <Th className="text-right">Calls</Th>
              <Th className="text-right">Failures</Th>
              <Th className="text-right">Prompt tokens</Th>
              <Th className="text-right">Completion tokens</Th>
              <Th className="text-right">Avg latency</Th>
              <Th className="text-right">Cost</Th>
            </tr>
          </thead>
          <tbody>
            {data?.tiers.map((t) => (
              <Tr key={t.tier}>
                <Td>
                  <span className="flex items-center gap-2">
                    <span className={cn("h-2.5 w-2.5", TIER_COLORS[t.tier])} />
                    {t.tier === "local" ? "Local model" : t.tier === "free" ? "Free API" : "Premium API"}
                  </span>
                </Td>
                <Td className="text-right font-mono tabular-nums">{num(t.calls)}</Td>
                <Td className="text-right font-mono tabular-nums">{num(t.failures)}</Td>
                <Td className="text-right font-mono tabular-nums">{num(t.prompt_tokens)}</Td>
                <Td className="text-right font-mono tabular-nums">{num(t.completion_tokens)}</Td>
                <Td className="text-right font-mono tabular-nums">{t.avg_latency_ms ? `${num(t.avg_latency_ms)} ms` : "-"}</Td>
                <Td className="text-right font-mono tabular-nums">{usd(t.cost_usd)}</Td>
              </Tr>
            ))}
          </tbody>
        </Table>
      </Panel>
    </div>
  );
}

// ------------------------------------------------------------------- audit

const PAGE = 50;

function AuditTab() {
  const [action, setAction] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [page, setPage] = useState(0);
  const params = new URLSearchParams({ limit: String(PAGE), offset: String(page * PAGE) });
  if (action) params.set("action", action);
  if (from) params.set("date_from", from);
  if (to) params.set("date_to", to);
  const { data } = useSWR<{ total: number; items: AuditLogOut[] }>(`/api/admin/audit-logs?${params}`);
  const exportParams = new URLSearchParams(params);
  exportParams.delete("limit");
  exportParams.delete("offset");

  return (
    <>
      <div className="mb-4 flex flex-wrap items-end gap-3">
        <Field label="Action">
          <Select value={action} onChange={(e) => { setAction(e.target.value); setPage(0); }} className="w-48">
            <option value="">All actions</option>
            <option value="auth.">Sign-ins</option>
            <option value="chat.">Questions</option>
            <option value="file.">Files</option>
            <option value="access.">Access</option>
            <option value="admin.">Admin changes</option>
            <option value="rate_limit.">Rate limits</option>
          </Select>
        </Field>
        <Field label="From"><Input type="date" value={from} onChange={(e) => { setFrom(e.target.value); setPage(0); }} /></Field>
        <Field label="To"><Input type="date" value={to} onChange={(e) => { setTo(e.target.value); setPage(0); }} /></Field>
        <div className="ml-auto">
          <Button variant="secondary" onClick={() => void downloadUrl(`/api/admin/audit-logs/export?${exportParams}`)}>
            <Download className="h-4 w-4" strokeWidth={1.5} /> Export CSV
          </Button>
        </div>
      </div>
      <div className="rounded-sm border border-line">
        {!data ? (
          <div className="space-y-2 p-4">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-9" />)}</div>
        ) : data.items.length === 0 ? (
          <Empty title="No events">Nothing matches these filters.</Empty>
        ) : (
          <Table>
            <thead>
              <tr>
                <Th>Time</Th>
                <Th>Who</Th>
                <Th>Action</Th>
                <Th>Detail</Th>
                <Th>IP</Th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((l) => (
                <Tr key={l.id}>
                  <Td className="whitespace-nowrap font-mono text-xs text-ink-2">{dateTime(l.created_at)}</Td>
                  <Td className="max-w-[200px] truncate">{l.user_email ?? <span className="text-ink-3">system</span>}</Td>
                  <Td>
                    <span className={cn("rounded-xs px-1.5 py-0.5 font-mono text-[11.5px]", l.action?.includes("fail") || l.action?.includes("rate_limit") || l.action?.includes("denied") ? "bg-danger-soft text-danger" : "bg-wash text-ink")}>
                      {l.action}
                    </span>
                  </Td>
                  <Td className="max-w-[420px] truncate font-mono text-xs text-ink-2" >
                    {l.details ? summarize(l.details) : "-"}
                  </Td>
                  <Td className="font-mono text-xs text-ink-2">{l.ip_address ?? "-"}</Td>
                </Tr>
              ))}
            </tbody>
          </Table>
        )}
      </div>
      {data && data.total > PAGE && (
        <div className="mt-4 flex items-center justify-between text-sm text-ink-2">
          <span className="font-mono text-xs">
            {page * PAGE + 1}–{Math.min((page + 1) * PAGE, data.total)} of {num(data.total)}
          </span>
          <div className="flex gap-2">
            <Button size="sm" variant="secondary" disabled={page === 0} onClick={() => setPage((p) => p - 1)}>Previous</Button>
            <Button size="sm" variant="secondary" disabled={(page + 1) * PAGE >= data.total} onClick={() => setPage((p) => p + 1)}>Next</Button>
          </div>
        </div>
      )}
    </>
  );
}

function summarize(d: Record<string, unknown>): string {
  if (typeof d.query === "string") return `“${d.query}”${d.tier ? ` · ${d.tier}` : ""}${d.mode ? ` · ${d.mode}` : ""}`;
  if (typeof d.name === "string") return d.name;
  return Object.entries(d)
    .filter(([, v]) => v !== null && v !== undefined && v !== "")
    .map(([k, v]) => `${k}=${typeof v === "object" ? JSON.stringify(v) : String(v)}`)
    .join("  ");
}

// ------------------------------------------------------------------ system

function SystemTab() {
  const { data: s } = useSWR<Stats>("/api/admin/stats");
  const { data: meta } = useSWR<Meta>("/api/system/meta");
  if (!s) return <Skeleton className="h-64" />;
  const maxDept = Math.max(1, ...s.users_by_department.map((d) => d.count));
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 divide-x divide-y divide-line overflow-hidden rounded-sm border border-line lg:grid-cols-4 lg:divide-y-0">
        <Stat label="People" value={num(s.users_total)} hint={`${num(s.users_active)} active`} />
        <Stat label="Documents" value={num(s.files_total)} hint={`${num(s.files_ready)} ready · ${num(s.files_failed)} failed`} />
        <Stat label="Indexed passages" value={num(s.chunks_total)} hint={`${num(s.files_in_progress)} files in queue`} />
        <Stat accent label="Questions · 24h" value={num(s.queries_24h)} hint={`${num(s.uploads_7d)} uploads this week`} />
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        <Panel eyebrow="People" title="By department">
          <div className="space-y-3">
            {s.users_by_department.map((d) => (
              <div key={d.department} className="flex items-center gap-3 text-sm">
                <span className="w-40 truncate text-ink">{d.department}</span>
                <span className="h-2 flex-1 bg-wash">
                  <span className="block h-full bg-ink" style={{ width: `${(d.count / maxDept) * 100}%` }} />
                </span>
                <span className="w-8 text-right font-mono text-xs text-ink-2">{d.count}</span>
              </div>
            ))}
          </div>
        </Panel>
        <Panel eyebrow="Instance" title="Configuration">
          <dl className="divide-y divide-line text-sm">
            {[
              ["Product", `${meta?.app_name ?? "Strata"} ${meta?.version ?? ""}`],
              ["Authentication", meta?.auth_provider === "local" ? "Built-in (on-prem)" : "Supabase"],
              ["Minimum password length", String(meta?.password_min_length ?? "-")],
            ].map(([k, v]) => (
              <div key={k} className="flex justify-between py-2.5">
                <dt className="text-ink-2">{k}</dt>
                <dd className="font-mono text-[13px] text-ink">{v}</dd>
              </div>
            ))}
          </dl>
        </Panel>
      </div>
    </div>
  );
}
