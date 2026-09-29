"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";

import { RequireAuth } from "@/components/RequireAuth";
import { api } from "@/lib/api";
import { clearToken } from "@/lib/auth";

const NAV = [
  { href: "/chat", label: "Chat" },
  { href: "/documents", label: "Documents" },
];

interface AppShellProps {
  children: ReactNode;
  /** Extra sidebar content under the navigation (e.g. the conversation list). */
  sidebar?: ReactNode;
}

function Sidebar({ sidebar, onNavigate }: { sidebar?: ReactNode; onNavigate?: () => void }) {
  const pathname = usePathname();
  const [email, setEmail] = useState<string | null>(null);

  useEffect(() => {
    api
      .me()
      .then((u) => setEmail(u.email))
      .catch(() => setEmail(null));
  }, []);

  return (
    <div className="flex h-full flex-col">
      <div className="px-4 pt-5 pb-4">
        <Link href="/chat" className="font-serif text-xl" onClick={onNavigate}>
          DocMind <span className="bg-marker px-1">AI</span>
        </Link>
      </div>
      <nav aria-label="Main" className="flex flex-col gap-0.5 px-2">
        {NAV.map((item) => {
          const active = pathname.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              onClick={onNavigate}
              aria-current={active ? "page" : undefined}
              className={`rounded-md px-3 py-1.5 text-sm ${
                active ? "bg-line/60 font-medium text-ink" : "text-muted hover:bg-line/40 hover:text-ink"
              }`}
            >
              {item.label}
            </Link>
          );
        })}
      </nav>
      <div className="mt-4 min-h-0 flex-1 overflow-y-auto border-t border-line px-2 pt-3">{sidebar}</div>
      <div className="flex items-center justify-between gap-2 border-t border-line px-4 py-3 text-sm">
        <span className="truncate text-muted" title={email ?? undefined}>
          {email ?? ""}
        </span>
        <button type="button" onClick={clearToken} className="shrink-0 text-muted hover:text-ink">
          Sign out
        </button>
      </div>
    </div>
  );
}

/** Authenticated layout: sidebar on desktop, slide-over drawer on mobile. */
export function AppShell({ children, sidebar }: AppShellProps) {
  const [drawerOpen, setDrawerOpen] = useState(false);

  return (
    <RequireAuth>
      <div className="flex h-dvh">
        <aside className="hidden w-64 shrink-0 border-r border-line bg-surface md:block">
          <Sidebar sidebar={sidebar} />
        </aside>

        {drawerOpen && (
          <div
            className="fixed inset-0 z-40 md:hidden"
            role="dialog"
            aria-modal="true"
            aria-label="Navigation"
          >
            <button
              type="button"
              aria-label="Close navigation"
              className="absolute inset-0 bg-ink/30"
              onClick={() => setDrawerOpen(false)}
            />
            <aside className="absolute inset-y-0 left-0 w-72 max-w-[85vw] bg-surface">
              <Sidebar sidebar={sidebar} onNavigate={() => setDrawerOpen(false)} />
            </aside>
          </div>
        )}

        <div className="flex min-w-0 flex-1 flex-col">
          <div className="flex items-center gap-3 border-b border-line bg-surface px-4 py-2.5 md:hidden">
            <button
              type="button"
              onClick={() => setDrawerOpen(true)}
              className="rounded-md px-2 py-1 text-sm text-muted hover:bg-line/50"
              aria-label="Open navigation"
            >
              Menu
            </button>
            <span className="font-serif">DocMind AI</span>
          </div>
          <main className="min-h-0 flex-1">{children}</main>
        </div>
      </div>
    </RequireAuth>
  );
}
