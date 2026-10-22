"use client";

import { ArrowRight, Eye, EyeOff } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/field";
import { ApiError, post } from "@/lib/api";

export function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (!email.includes("@") || !password) {
      setError("Enter your email and password.");
      return;
    }
    setLoading(true);
    try {
      await post("/api/auth/login", { email: email.trim(), password });
      const next = params.get("next");
      router.replace(next && next.startsWith("/") && !next.startsWith("//") ? next : "/overview");
      router.refresh();
    } catch (err) {
      setLoading(false);
      if (err instanceof ApiError && err.status === 401) setError("That email and password don't match.");
      else if (err instanceof ApiError && err.status === 429) setError(err.message);
      else if (err instanceof ApiError && err.status === 403) setError("This account is disabled. Contact your administrator.");
      else setError("Sign-in is unavailable right now. Try again in a moment.");
    }
  }

  return (
    <motion.form
      onSubmit={submit}
      noValidate
      className="mt-9 space-y-5"
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.55, delay: 0.2, ease: [0.2, 0.7, 0.2, 1] }}
    >
      <AnimatePresence>
        {error && (
          <motion.div
            role="alert"
            initial={{ opacity: 0, height: 0, x: 0 }}
            animate={{ opacity: 1, height: "auto", x: [0, -6, 6, -3, 3, 0] }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.35 }}
            className="flex items-start gap-2.5 overflow-hidden rounded-sm border border-danger/40 bg-danger-soft px-3.5 py-2.5 text-sm text-danger"
          >
            <span className="mt-[7px] h-1.5 w-1.5 shrink-0 bg-danger" />
            {error}
          </motion.div>
        )}
      </AnimatePresence>
      <Field label="Work email" htmlFor="email">
        <Input
          id="email"
          type="email"
          autoComplete="username"
          autoFocus
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="you@company.com"
          className="h-11 text-[15px]"
        />
      </Field>
      <Field label="Password" htmlFor="password">
        <div className="relative">
          <Input
            id="password"
            type={show ? "text" : "password"}
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="••••••••••••"
            className="h-11 pr-11 text-[15px]"
          />
          <button
            type="button"
            onClick={() => setShow((v) => !v)}
            className="absolute inset-y-0 right-0 grid w-11 place-items-center text-ink-2 hover:text-ink"
            aria-label={show ? "Hide password" : "Show password"}
          >
            {show ? <EyeOff className="h-4 w-4" strokeWidth={1.5} /> : <Eye className="h-4 w-4" strokeWidth={1.5} />}
          </button>
        </div>
      </Field>
      <Button type="submit" variant="primary" size="lg" loading={loading} className="w-full justify-center">
        {loading ? "Signing in" : "Sign in"}
        {!loading && <ArrowRight className="h-4 w-4" strokeWidth={1.75} />}
      </Button>
      <p className="text-center text-[13px] text-ink-2">Forgot your password? Ask your administrator to reset it.</p>
    </motion.form>
  );
}
