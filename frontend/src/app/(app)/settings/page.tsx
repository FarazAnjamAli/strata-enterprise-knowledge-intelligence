"use client";

import { useState } from "react";
import useSWR from "swr";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/field";
import { PageHeader, Panel } from "@/components/ui/panel";
import { useToast } from "@/components/ui/toast";
import { ApiError, post } from "@/lib/api";
import { useSession } from "@/lib/session";
import type { Meta } from "@/lib/types";

export default function SettingsPage() {
  const toast = useToast();
  const { profile } = useSession();
  const { data: meta } = useSWR<Meta>("/api/system/meta");
  const [cur, setCur] = useState("");
  const [next, setNext] = useState("");
  const [again, setAgain] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function change(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    if (next !== again) return setErr("The new passwords don't match.");
    setSaving(true);
    try {
      await post("/api/auth/password", { current_password: cur, new_password: next });
      setCur("");
      setNext("");
      setAgain("");
      toast("ok", "Password changed. Other sessions were signed out.");
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Couldn't change password");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="mx-auto w-full max-w-[880px] px-10 py-10">
      <PageHeader eyebrow="Account" title="Settings" />
      <div className="space-y-6">
        <Panel eyebrow="Profile" title="Your account">
          <dl className="grid grid-cols-2 gap-x-8 gap-y-4 text-sm">
            {[
              ["Name", profile?.full_name || "-"],
              ["Email", profile?.email],
              ["Role", profile?.role],
              ["Department", profile?.department || "Unassigned"],
            ].map(([k, v]) => (
              <div key={k}>
                <dt className="font-mono text-2xs uppercase text-ink-2">{k}</dt>
                <dd className="mt-1 text-ink">{v}</dd>
              </div>
            ))}
          </dl>
          <p className="mt-5 border-t border-line pt-4 text-[13px] text-ink-2">Role and department are managed by your administrator.</p>
        </Panel>

        {meta?.auth_provider === "local" && (
          <Panel eyebrow="Security" title="Change password">
            <form onSubmit={change} className="max-w-sm space-y-4">
              <Field label="Current password">
                <Input type="password" value={cur} onChange={(e) => setCur(e.target.value)} autoComplete="current-password" />
              </Field>
              <Field label="New password" hint={`At least ${meta.password_min_length} characters, mixing cases, digits or symbols.`}>
                <Input type="password" value={next} onChange={(e) => setNext(e.target.value)} autoComplete="new-password" />
              </Field>
              <Field label="Repeat new password" error={err}>
                <Input type="password" value={again} onChange={(e) => setAgain(e.target.value)} autoComplete="new-password" />
              </Field>
              <Button type="submit" variant="primary" loading={saving} disabled={!cur || !next}>
                Update password
              </Button>
            </form>
          </Panel>
        )}

        <Panel eyebrow="Sessions" title="Sign out everywhere">
          <div className="flex items-center justify-between gap-6">
            <p className="text-sm text-ink-2">Ends every session on every device, including this one.</p>
            <Button
              variant="danger"
              onClick={async () => {
                await post("/api/auth/logout-everywhere").catch(() => {});
                window.location.href = "/login";
              }}
            >
              Sign out everywhere
            </Button>
          </div>
        </Panel>
      </div>
    </div>
  );
}
