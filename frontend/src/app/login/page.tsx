import type { Metadata } from "next";
import { Suspense } from "react";
import { Logo } from "@/components/brand";
import { LoginForm } from "./login-form";
import { LoginIntro } from "./login-intro";
import { TierVisual } from "./tier-visual";

export const metadata: Metadata = { title: "Sign in" };

export default function LoginPage() {
  return (
    <div className="grid min-h-dvh grid-cols-1 bg-white lg:grid-cols-[minmax(440px,520px)_1fr]">
      <div className="flex flex-col px-8 py-8 sm:px-14">
        <Logo animated />
        <div className="flex flex-1 flex-col justify-center py-16">
          <div className="w-full max-w-[360px]">
            <LoginIntro />
            <Suspense>
              <LoginForm />
            </Suspense>
          </div>
        </div>
        <div className="flex items-center justify-between font-mono text-[11px] text-ink-3">
          <span>On-prem first · encrypted at rest</span>
          <span>v2.0</span>
        </div>
      </div>
      <TierVisual />
    </div>
  );
}
