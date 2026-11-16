import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "NDA Playbook Reviewer",
  description: "First-pass NDA review against a company playbook: verdicts, evidence, redlines and a memo.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="min-h-full flex flex-col">
        <header className="border-b border-line bg-surface">
          <div className="mx-auto flex max-w-[1500px] items-center gap-6 px-4 py-3">
            <Link href="/" className="flex items-center gap-2 font-semibold text-ink">
              <svg width="22" height="22" viewBox="0 0 24 24" aria-hidden="true">
                <path
                  d="M6 2h9l5 5v15H6z"
                  fill="none"
                  stroke="var(--accent)"
                  strokeWidth="1.8"
                  strokeLinejoin="round"
                />
                <path d="M9 12h8M9 16h6" stroke="var(--accent)" strokeWidth="1.8" strokeLinecap="round" />
              </svg>
              NDA Playbook Reviewer
            </Link>
            <nav className="flex gap-1 text-sm">
              <Link href="/" className="rounded-md px-3 py-1.5 text-ink-2 hover:bg-surface-2 hover:text-ink">
                Review
              </Link>
              <Link
                href="/evaluation"
                className="rounded-md px-3 py-1.5 text-ink-2 hover:bg-surface-2 hover:text-ink"
              >
                Evaluation
              </Link>
            </nav>
            <span className="ml-auto hidden text-xs text-muted sm:block">
              Draft for a lawyer, not legal advice
            </span>
          </div>
        </header>
        <main className="flex-1">{children}</main>
      </body>
    </html>
  );
}
