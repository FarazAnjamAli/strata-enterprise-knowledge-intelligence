import type { Metadata, Viewport } from "next";
// Self-hosted fonts (bundled at build time - no Google Fonts call, works air-gapped)
import "@fontsource-variable/instrument-sans";
import "@fontsource-variable/jetbrains-mono";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "Strata", template: "%s · Strata" },
  description: "Three-tier, on-prem-first knowledge assistant. Answers from your documents, with sources.",
  robots: { index: false, follow: false },
};

export const viewport: Viewport = { themeColor: "#FFFFFF" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
