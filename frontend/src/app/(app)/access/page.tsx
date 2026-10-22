"use client";

import { Check, Clock, KeyRound, Plus, Search, Trash2, X } from "lucide-react";
import { useMemo, useState } from "react";
import useSWR from "swr";
import { FileIcon } from "@/components/files/file-icon";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Empty, Skeleton } from "@/components/ui/empty";
import { Field, Input, Select } from "@/components/ui/field";
import { PageHeader } from "@/components/ui/panel";
import { Tabs } from "@/components/ui/tabs";
import { Table, Td, Th, Tr } from "@/components/ui/table";
import { useToast } from "@/components/ui/toast";
import { ApiError, del, post } from "@/lib/api";
import { ago } from "@/lib/format";
import { useSession } from "@/lib/session";
import type { AccessRequestOut, AccessRuleOut, CatalogFile } from "@/lib/types";

type Tab = "discover" | "mine" | "inbox" | "rules";

function StatusBadge({ s }: { s: AccessRequestOut["status"] }) {
  if (s === "approved") return <Badge tone="lime">Approved</Badge>;
  if (s === "denied") return <Badge tone="danger">Denied</Badge>;
  return <Badge tone="amber" dot>Pending</Badge>;
}

export default function AccessPage() {
  const toast = useToast();
  const { isHead, status } = useSession();
  const [tab, setTab] = useState<Tab>("discover");
  const [q, setQ] = useState("");
  const [ruleOpen, setRuleOpen] = useState(false);

  const catalog = useSWR<CatalogFile[]>("/api/access/catalog");
  const mine = useSWR<AccessRequestOut[]>("/api/access?box=mine");
  const inbox = useSWR<AccessRequestOut[]>(isHead ? "/api/access?box=inbox" : null, { refreshInterval: 15_000 });
  const rules = useSWR<AccessRuleOut[]>(isHead ? "/api/access/rules" : null);

  const pending = inbox.data?.filter((r) => r.status === "pending") ?? [];
  const shown = useMemo(
    () =>
      (catalog.data ?? []).filter(
        (f) => !q || f.name.toLowerCase().includes(q.toLowerCase()) || (f.department ?? "").toLowerCase().includes(q.toLowerCase()),
      ),
    [catalog.data, q],
  );

  async function request(f: CatalogFile) {
    try {
      const r = await post<AccessRequestOut>("/api/access", { file_id: f.id });
      toast("ok", r.status === "approved" ? `Access granted to ${f.name} (standing rule)` : `Request sent to ${f.department} for approval`);
      void catalog.mutate();
      void mine.mutate();
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : "Request failed");
    }
  }

  async function decide(r: AccessRequestOut, decision: "approve_once" | "approve_recurring" | "deny") {
    try {
      await post(`/api/access/${r.id}/decide`, { decision });
      toast("ok", decision === "deny" ? "Request denied" : "Access granted");
      void inbox.mutate();
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : "Couldn't save decision");
    }
  }

  const tabs = [
    { value: "discover" as const, label: "Discover", count: catalog.data?.length ?? null },
    { value: "mine" as const, label: "My requests", count: mine.data?.length ?? null },
    ...(isHead
      ? [
          { value: "inbox" as const, label: "Approvals", count: pending.length || null },
          { value: "rules" as const, label: "Auto-approve rules", count: rules.data?.length ?? null },
        ]
      : []),
  ];

  return (
    <div className="mx-auto w-full max-w-[1180px] px-10 py-10">
      <PageHeader
        eyebrow="Access"
        title="Cross-team access"
        description="Find documents owned by other departments and request read access. Department heads approve once or on a recurring basis."
      />
      <Tabs value={tab} onChange={setTab} items={tabs} />

      <div className="mt-6">
        {tab === "discover" && (
          <>
            <div className="relative mb-4 w-80">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-2" strokeWidth={1.5} />
              <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search documents or departments" className="pl-9" />
            </div>
            <div className="rounded-sm border border-line">
              {!catalog.data ? (
                <div className="space-y-2 p-4">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-10" />)}</div>
              ) : shown.length === 0 ? (
                <Empty icon={<KeyRound className="h-5 w-5" strokeWidth={1.5} />} title="Nothing to request">
                  You already have access to every department document, or none have been shared at department level yet.
                </Empty>
              ) : (
                <Table>
                  <thead>
                    <tr>
                      <Th>Document</Th>
                      <Th>Owner</Th>
                      <Th>Your request</Th>
                      <Th className="w-40" />
                    </tr>
                  </thead>
                  <tbody>
                    {shown.map((f) => (
                      <Tr key={f.id}>
                        <Td>
                          <div className="flex items-center gap-3">
                            <FileIcon name={f.name} />
                            <span className="font-medium">{f.name}</span>
                          </div>
                        </Td>
                        <Td className="text-ink-2">{f.department}</Td>
                        <Td>{f.my_request_status ? <StatusBadge s={f.my_request_status} /> : <span className="text-ink-3">-</span>}</Td>
                        <Td className="text-right">
                          {f.my_request_status === "pending" ? (
                            <span className="inline-flex items-center gap-1.5 text-xs text-ink-2">
                              <Clock className="h-3.5 w-3.5" /> Awaiting approval
                            </span>
                          ) : (
                            <Button size="sm" variant="secondary" onClick={() => void request(f)}>
                              Request access
                            </Button>
                          )}
                        </Td>
                      </Tr>
                    ))}
                  </tbody>
                </Table>
              )}
            </div>
          </>
        )}

        {tab === "mine" && (
          <div className="rounded-sm border border-line">
            {!mine.data?.length ? (
              <Empty title="No requests yet">Requests you make from the Discover tab show up here.</Empty>
            ) : (
              <Table>
                <thead>
                  <tr>
                    <Th>Document</Th>
                    <Th>Department</Th>
                    <Th>Status</Th>
                    <Th>Requested</Th>
                    <Th>Expires</Th>
                  </tr>
                </thead>
                <tbody>
                  {mine.data.map((r) => (
                    <Tr key={r.id}>
                      <Td className="font-medium">{r.file_name}</Td>
                      <Td className="text-ink-2">{r.department}</Td>
                      <Td><StatusBadge s={r.status} /></Td>
                      <Td className="text-ink-2">{ago(r.requested_at)}</Td>
                      <Td className="font-mono text-xs text-ink-2">
                        {r.status === "approved" ? (r.expires_at ? new Date(r.expires_at).toLocaleString() : "never") : "-"}
                      </Td>
                    </Tr>
                  ))}
                </tbody>
              </Table>
            )}
          </div>
        )}

        {tab === "inbox" && (
          <div className="rounded-sm border border-line">
            {!inbox.data?.length ? (
              <Empty icon={<Check className="h-5 w-5" strokeWidth={1.5} />} title="All caught up">No access requests for your department.</Empty>
            ) : (
              <Table>
                <thead>
                  <tr>
                    <Th>Requester</Th>
                    <Th>Document</Th>
                    <Th>Status</Th>
                    <Th>Requested</Th>
                    <Th className="w-[330px]" />
                  </tr>
                </thead>
                <tbody>
                  {inbox.data.map((r) => (
                    <Tr key={r.id}>
                      <Td className="font-medium">{r.requester_email}</Td>
                      <Td>{r.file_name}</Td>
                      <Td><StatusBadge s={r.status} /></Td>
                      <Td className="text-ink-2">{ago(r.requested_at)}</Td>
                      <Td>
                        {r.status === "pending" ? (
                          <div className="flex justify-end gap-1.5">
                            <Button size="sm" variant="primary" onClick={() => void decide(r, "approve_once")}>Approve 24h</Button>
                            <Button size="sm" variant="secondary" onClick={() => void decide(r, "approve_recurring")}>Always</Button>
                            <Button size="sm" variant="danger" onClick={() => void decide(r, "deny")}>
                              <X className="h-3.5 w-3.5" /> Deny
                            </Button>
                          </div>
                        ) : (
                          <p className="text-right font-mono text-xs text-ink-3">{r.is_recurring ? "recurring" : r.expires_at ? `until ${new Date(r.expires_at).toLocaleString()}` : ""}</p>
                        )}
                      </Td>
                    </Tr>
                  ))}
                </tbody>
              </Table>
            )}
          </div>
        )}

        {tab === "rules" && (
          <>
            <div className="mb-4 flex items-center justify-between">
              <p className="max-w-xl text-sm text-ink-2">
                Standing rules approve matching requests instantly, before anyone has to look at them.
              </p>
              <Button variant="primary" onClick={() => setRuleOpen(true)}>
                <Plus className="h-4 w-4" /> New rule
              </Button>
            </div>
            <div className="rounded-sm border border-line">
              {!rules.data?.length ? (
                <Empty title="No rules yet">Every request currently needs a manual decision.</Empty>
              ) : (
                <Table>
                  <thead>
                    <tr>
                      <Th>Rule</Th>
                      <Th>Department</Th>
                      <Th>Requester role</Th>
                      <Th>File type</Th>
                      <Th>Grant</Th>
                      <Th className="w-12" />
                    </tr>
                  </thead>
                  <tbody>
                    {rules.data.map((r) => (
                      <Tr key={r.id}>
                        <Td className="font-medium">{r.rule_name}</Td>
                        <Td className="text-ink-2">{r.department}</Td>
                        <Td>{r.source_role ?? <span className="text-ink-3">any</span>}</Td>
                        <Td className="font-mono text-xs">{r.target_file_type ?? "any"}</Td>
                        <Td className="font-mono text-xs">{r.grant_hours ? `${r.grant_hours}h` : "no expiry"}</Td>
                        <Td>
                          <Button
                            size="icon"
                            variant="ghost"
                            aria-label="Delete rule"
                            onClick={async () => {
                              await del(`/api/access/rules/${r.id}`).catch(() => {});
                              void rules.mutate();
                            }}
                          >
                            <Trash2 className="h-4 w-4" strokeWidth={1.5} />
                          </Button>
                        </Td>
                      </Tr>
                    ))}
                  </tbody>
                </Table>
              )}
            </div>
          </>
        )}
      </div>

      <RuleDialog
        open={ruleOpen}
        onClose={() => setRuleOpen(false)}
        roles={status?.roles ?? []}
        onCreated={() => {
          setRuleOpen(false);
          void rules.mutate();
          toast("ok", "Rule created");
        }}
      />
    </div>
  );
}

function RuleDialog({ open, onClose, roles, onCreated }: { open: boolean; onClose: () => void; roles: string[]; onCreated: () => void }) {
  const [name, setName] = useState("");
  const [role, setRole] = useState("");
  const [type, setType] = useState("");
  const [hours, setHours] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  async function save() {
    if (!name.trim()) return setErr("Give the rule a name.");
    setSaving(true);
    try {
      await post("/api/access/rules", {
        rule_name: name.trim(),
        source_role: role || null,
        target_file_type: type.trim().replace(/^\./, "") || null,
        grant_hours: hours ? Number(hours) : null,
      });
      setName("");
      setRole("");
      setType("");
      setHours("");
      setErr(null);
      onCreated();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Couldn't create rule");
    } finally {
      setSaving(false);
    }
  }
  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="New auto-approve rule"
      description="Applies to requests for your department's documents."
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button variant="primary" loading={saving} onClick={() => void save()}>Create rule</Button>
        </>
      }
    >
      <div className="space-y-4">
        <Field label="Name" error={err}>
          <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Managers can read spreadsheets" />
        </Field>
        <div className="grid grid-cols-2 gap-4">
          <Field label="Requester role">
            <Select value={role} onChange={(e) => setRole(e.target.value)}>
              <option value="">Any role</option>
              {roles.map((r) => (
                <option key={r}>{r}</option>
              ))}
            </Select>
          </Field>
          <Field label="File type" hint="e.g. pdf · blank = any">
            <Input value={type} onChange={(e) => setType(e.target.value)} placeholder="any" />
          </Field>
        </div>
        <Field label="Grant duration (hours)" hint="Blank = no expiry">
          <Input type="number" min={1} value={hours} onChange={(e) => setHours(e.target.value)} placeholder="no expiry" />
        </Field>
      </div>
    </Dialog>
  );
}
