import Link from "next/link";
import { Logo } from "@/components/brand";

export default function NotFound() {
  return (
    <div className="grid-lines grid min-h-dvh place-items-center bg-paper p-8">
      <div className="w-full max-w-md rounded-sm border border-ink bg-white p-10 shadow-pop">
        <Logo size="sm" />
        <p className="mt-10 font-mono text-2xs uppercase text-ink-2">Error 404</p>
        <h1 className="mt-2 text-[28px] font-medium tracking-[-0.02em] text-ink">This page doesn&apos;t exist.</h1>
        <Link href="/overview" className="mt-6 inline-block text-sm text-ink underline decoration-lime decoration-2 underline-offset-4">
          Back to overview →
        </Link>
      </div>
    </div>
  );
}
