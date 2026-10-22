"use client";

import { CloudUpload, ExternalLink, FileText, MessageSquare, RotateCw, Search, Trash2 } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import Link from "next/link";
import { CropMarks, Reveal } from "@/components/motion";
import { useCallback, useMemo, useRef, useState } from "react";
import useSWR from "swr";
import { FileIcon } from "@/components/files/file-icon";
import { AccessBadge, IndexBadge, accessLabel } from "@/components/files/status";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Empty, Skeleton } from "@/components/ui/empty";
import { Input, Select } from "@/components/ui/field";
import { PageHeader } from "@/components/ui/panel";
import { Segmented } from "@/components/ui/tabs";
import { Table, Td, Th } from "@/components/ui/table";
import { useToast } from "@/components/ui/toast";
import { ApiError, api, del, openFile, patch, post } from "@/lib/api";
import { cn } from "@/lib/cn";
import { ago, bytes, ext } from "@/lib/format";
import { useSession } from "@/lib/session";
import type { AccessLevel, FileOut } from "@/lib/types";

type Upload = { key: string; name: string; size: number; progress: number; state: "uploading" | "done" | "error"; error?: string };

function uploadOne(file: File, access: AccessLevel, onProgress: (p: number) => void): Promise<void> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/upload");
    xhr.setRequestHeader("X-Strata-CSRF", "1");
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress(e.loaded / e.total);
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) return resolve();
      let msg = "Upload failed";
      try {
        const d = JSON.parse(xhr.responseText).detail;
        msg = typeof d === "string" ? d : msg;
      } catch {
        /* keep default */
      }
      reject(new Error(msg));
    };
    xhr.onerror = () => reject(new Error("Network error"));
    const form = new FormData();
    form.append("file", file);
    form.append("access_level", access);
    xhr.send(form);
  });
}

export default function LibraryPage() {
  const toast = useToast();
  const { profile, status, isAdmin, isHead } = useSession();
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<"all" | "ready" | "working" | "failed">("all");
  const [access, setAccess] = useState<AccessLevel>("department");
  const [uploads, setUploads] = useState<Upload[]>([]);
  const [drag, setDrag] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState<FileOut | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const { data: files, mutate } = useSWR<FileOut[]>("/api/files?limit=1000", {
    refreshInterval: (d) => (d?.some((f) => f.index_status === "pending" || f.index_status === "processing") ? 2500 : 0),
  });

  const effectiveAccess: AccessLevel = !profile?.department && access === "department" ? "private" : access;

  const startUploads = useCallback(
    async (list: FileList | File[]) => {
      const arr = Array.from(list);
      if (!arr.length) return;
      await api("/api/auth/me").catch(() => {}); // make sure the session is fresh
      const maxMb = status?.max_file_size_mb ?? 50;
      const allowed = new Set(status?.allowed_extensions ?? []);
      for (const f of arr) {
        const key = `${f.name}-${f.size}-${Date.now()}-${Math.random()}`;
        const bad =
          allowed.size && !allowed.has(ext(f.name))
            ? `.${ext(f.name) || "?"} files aren't supported`
            : f.size > maxMb * 1024 * 1024
              ? `Larger than ${maxMb} MB`
              : null;
        setUploads((u) => [{ key, name: f.name, size: f.size, progress: 0, state: bad ? "error" : "uploading", error: bad ?? undefined }, ...u]);
        if (bad) continue;
        try {
          await uploadOne(f, effectiveAccess, (p) => setUploads((u) => u.map((x) => (x.key === key ? { ...x, progress: p } : x))));
          setUploads((u) => u.map((x) => (x.key === key ? { ...x, progress: 1, state: "done" } : x)));
          void mutate();
        } catch (err) {
          setUploads((u) => u.map((x) => (x.key === key ? { ...x, state: "error", error: (err as Error).message } : x)));
        }
      }
    },
    [effectiveAccess, mutate, status],
  );

  const shown = useMemo(() => {
    const q = query.toLowerCase();
    return (files ?? []).filter((f) => {
      if (q && !f.name.toLowerCase().includes(q) && !(f.department ?? "").toLowerCase().includes(q)) return false;
      if (filter === "ready") return f.index_status === "ready";
      if (filter === "failed") return f.index_status === "failed";
      if (filter === "working") return f.index_status === "pending" || f.index_status === "processing";
      return true;
    });
  }, [files, query, filter]);

  const canManage = (f: FileOut) =>
    isAdmin || f.owner_id === profile?.id || (profile?.role === "Department Head" && f.department === profile.department);

  async function changeAccess(f: FileOut, level: AccessLevel) {
    try {
      await patch(`/api/files/${f.id}`, { access_level: level });
      toast("ok", `${f.name} is now ${accessLabel(level).toLowerCase()}-visible`);
      void mutate();
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : "Couldn't change access");
    }
  }

  async function reindex(f: FileOut) {
    try {
      await post(`/api/files/${f.id}/reindex`);
      toast("ok", `Re-indexing ${f.name}`);
      void mutate();
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : "Couldn't reindex");
    }
  }

  async function remove(f: FileOut) {
    try {
      await del(`/api/files/${f.id}`);
      toast("ok", `Deleted ${f.name}`);
      setConfirmDelete(null);
      void mutate();
    } catch (e) {
      toast("error", e instanceof ApiError ? e.message : "Couldn't delete");
    }
  }

  const counts = {
    all: files?.length ?? 0,
    ready: files?.filter((f) => f.index_status === "ready").length ?? 0,
    working: files?.filter((f) => f.index_status === "pending" || f.index_status === "processing").length ?? 0,
    failed: files?.filter((f) => f.index_status === "failed").length ?? 0,
  };

  return (
    <div className="mx-auto w-full max-w-[1280px] px-10 py-10">
      <PageHeader
        eyebrow="Library"
        title="Documents"
        description="Everything you can query. New files are parsed, chunked and embedded in the background, usually within a minute."
      />

      {/* upload */}
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDrag(true);
        }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDrag(false);
          void startUploads(e.dataTransfer.files);
        }}
        className={cn(
          "relative grid gap-6 overflow-hidden rounded-sm p-6 transition-colors duration-300 lg:grid-cols-[1fr_auto]",
          drag ? "bg-lime-soft" : "bg-paper",
        )}
      >
        {/* marching-ants border: crawls while a file hovers over the zone */}
        <svg aria-hidden className="pointer-events-none absolute inset-0 h-full w-full">
          <rect
            x="0.5"
            y="0.5"
            style={{ width: "calc(100% - 1px)", height: "calc(100% - 1px)" }}
            fill="none"
            stroke={drag ? "#0A0A0A" : "#CDCDC7"}
            strokeWidth={drag ? 1.5 : 1}
            strokeDasharray="8 4"
            className={drag ? "animate-march" : ""}
          />
        </svg>
        <div className="dots pointer-events-none absolute inset-0 opacity-40" />
        {drag && <CropMarks />}
        <div className="flex items-center gap-5">
          <motion.div
            animate={drag ? { y: -4, rotate: -4 } : { y: 0, rotate: 0 }}
            transition={{ type: "spring", stiffness: 400, damping: 20 }}
            className={cn("relative grid h-12 w-12 shrink-0 place-items-center rounded-sm border border-ink", drag ? "bg-lime" : "bg-white")}
          >
            <CloudUpload className="h-5 w-5 text-ink" strokeWidth={1.5} />
          </motion.div>
          <div>
            <p className="text-[15px] font-medium text-ink">Drop files here, or browse</p>
            <p className="mt-0.5 text-sm text-ink-2">
              PDF, Word, Excel, CSV, Markdown, JSON, XML, images (OCR) and video (metadata) · up to {status?.max_file_size_mb ?? 50} MB each
            </p>
          </div>
        </div>
        <div className="relative flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-2">
            <span className="font-mono text-2xs uppercase text-ink-2">Visible to</span>
            <Segmented
              value={effectiveAccess}
              onChange={setAccess}
              items={[
                ...(profile?.department ? [{ value: "department" as const, label: profile.department }] : []),
                ...(isHead ? [{ value: "public" as const, label: "Everyone" }] : []),
                { value: "private" as const, label: "Only me" },
              ]}
            />
          </div>
          <input ref={inputRef} type="file" multiple hidden onChange={(e) => e.target.files && void startUploads(e.target.files)} />
          <Button variant="primary" onClick={() => inputRef.current?.click()}>
            Browse files
          </Button>
        </div>
      </div>

      {uploads.length > 0 && (
        <div className="mt-3 divide-y divide-line rounded-sm border border-line">
          <AnimatePresence initial={false}>
          {uploads.slice(0, 6).map((u) => (
            <motion.div
              key={u.key}
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              className="flex items-center gap-4 overflow-hidden px-4 py-2.5 text-sm"
            >
              <FileIcon name={u.name} className="h-6 w-6 text-[8px]" />
              <span className="min-w-0 flex-1 truncate text-ink">{u.name}</span>
              <span className="font-mono text-[11px] text-ink-2">{bytes(u.size)}</span>
              {u.state === "uploading" && (
                <span className="relative h-1 w-32 overflow-hidden bg-wash">
                  <span className="block h-full bg-ink transition-all duration-300" style={{ width: `${Math.round(u.progress * 100)}%` }} />
                  <span className="absolute inset-0 animate-scan bg-gradient-to-r from-transparent via-lime/80 to-transparent" />
                </span>
              )}
              {u.state === "done" && <span className="font-mono text-[11px] text-ink">uploaded → indexing</span>}
              {u.state === "error" && <span className="text-xs text-danger">{u.error}</span>}
            </motion.div>
          ))}
          </AnimatePresence>
          <div className="flex justify-end px-4 py-1.5">
            <button className="text-xs text-ink-2 hover:text-ink" onClick={() => setUploads([])}>
              Clear
            </button>
          </div>
        </div>
      )}

      {/* list */}
      <div className="mt-8 flex flex-wrap items-center justify-between gap-3">
        <Segmented
          value={filter}
          onChange={setFilter}
          items={[
            { value: "all", label: `All ${counts.all}` },
            { value: "ready", label: `Ready ${counts.ready}` },
            { value: "working", label: `Indexing ${counts.working}` },
            { value: "failed", label: `Failed ${counts.failed}` },
          ]}
        />
        <div className="relative w-72">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-2" strokeWidth={1.5} />
          <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Filter by name or department" className="pl-9" />
        </div>
      </div>

      <Reveal className="mt-4 rounded-sm border border-line">
        {!files ? (
          <div className="space-y-2 p-4">
            {[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-11" />)}
          </div>
        ) : shown.length === 0 ? (
          <Empty icon={<FileText className="h-5 w-5" strokeWidth={1.5} />} title={files.length ? "Nothing matches" : "No documents yet"}>
            {files.length ? "Try a different filter." : "Upload a file above to get started."}
          </Empty>
        ) : (
          <Table>
            <thead>
              <tr>
                <Th>Name</Th>
                <Th>Department</Th>
                <Th>Visibility</Th>
                <Th>Status</Th>
                <Th className="text-right">Passages</Th>
                <Th>Added</Th>
                <Th className="w-[160px]" />
              </tr>
            </thead>
            <tbody>
              {shown.map((f, i) => (
                <motion.tr
                  key={f.id}
                  layout="position"
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.35, delay: Math.min(i, 12) * 0.035 }}
                  className="group transition-colors hover:bg-paper"
                >
                  <Td>
                    <div className="flex items-center gap-3">
                      <FileIcon name={f.name} />
                      <div className="min-w-0">
                        <button onClick={() => void openFile(f.id)} className="block max-w-[340px] truncate text-left font-medium text-ink hover:underline">
                          {f.name}
                        </button>
                        <p className="font-mono text-[11px] text-ink-2">{bytes(f.file_size_bytes)}</p>
                        {f.index_status === "failed" && f.index_error && (
                          <p className="max-w-[340px] truncate text-xs text-danger" title={f.index_error}>
                            {f.index_error}
                          </p>
                        )}
                      </div>
                    </div>
                  </Td>
                  <Td className="text-ink-2">{f.department ?? "-"}</Td>
                  <Td>
                    {canManage(f) && (isHead || f.access_level !== "public") ? (
                      <Select
                        value={f.access_level ?? "private"}
                        onChange={(e) => void changeAccess(f, e.target.value as AccessLevel)}
                        className="h-8 w-[136px] text-[13px]"
                        aria-label="Visibility"
                      >
                        <option value="department">Department</option>
                        {isHead && <option value="public">Company</option>}
                        <option value="private">Private</option>
                      </Select>
                    ) : (
                      <AccessBadge level={f.access_level} />
                    )}
                  </Td>
                  <Td>
                    <IndexBadge status={f.index_status} />
                  </Td>
                  <Td className="text-right font-mono text-[13px] tabular-nums text-ink-2">{f.chunk_count || "-"}</Td>
                  <Td className="whitespace-nowrap text-ink-2">{ago(f.created_at)}</Td>
                  <Td>
                    <div className="flex justify-end gap-0.5 opacity-60 transition-opacity group-hover:opacity-100">
                      {f.index_status === "ready" && (
                        <Link href={`/chat?file=${f.id}&name=${encodeURIComponent(f.name)}`} title="Ask this document">
                          <Button size="icon" variant="ghost" aria-label="Ask this document">
                            <MessageSquare className="h-4 w-4" strokeWidth={1.5} />
                          </Button>
                        </Link>
                      )}
                      <Button size="icon" variant="ghost" onClick={() => void openFile(f.id)} aria-label="Open">
                        <ExternalLink className="h-4 w-4" strokeWidth={1.5} />
                      </Button>
                      {canManage(f) && (
                        <>
                          <Button size="icon" variant="ghost" onClick={() => void reindex(f)} aria-label="Re-index" title="Re-index">
                            <RotateCw className="h-4 w-4" strokeWidth={1.5} />
                          </Button>
                          <Button size="icon" variant="ghost" onClick={() => setConfirmDelete(f)} aria-label="Delete" className="hover:text-danger">
                            <Trash2 className="h-4 w-4" strokeWidth={1.5} />
                          </Button>
                        </>
                      )}
                    </div>
                  </Td>
                </motion.tr>
              ))}
            </tbody>
          </Table>
        )}
      </Reveal>

      <Dialog
        open={!!confirmDelete}
        onClose={() => setConfirmDelete(null)}
        title="Delete document?"
        description={confirmDelete ? <>“{confirmDelete.name}” and its indexed passages will be removed permanently.</> : null}
        footer={
          <>
            <Button variant="secondary" onClick={() => setConfirmDelete(null)}>
              Cancel
            </Button>
            <Button variant="primary" className="!bg-danger !border-danger" onClick={() => confirmDelete && void remove(confirmDelete)}>
              Delete
            </Button>
          </>
        }
      >
        <p className="text-sm text-ink-2">Answers that cited this document will no longer link to it. This can&apos;t be undone.</p>
      </Dialog>
    </div>
  );
}
