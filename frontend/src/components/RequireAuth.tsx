"use client";

import { useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";

import { useAuth } from "@/lib/auth";

/**
 * Client-side route guard. The token lives in localStorage, which the server
 * can't read, so protection happens after hydration. This is a UX guard only:
 * the real enforcement is the backend rejecting requests without a valid JWT.
 */
export function RequireAuth({ children }: { children: ReactNode }) {
  const { ready, token } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (ready && !token) router.replace("/login");
  }, [ready, token, router]);

  if (!ready || !token) {
    return <div className="grid min-h-dvh place-items-center text-sm text-muted">Loading…</div>;
  }
  return <>{children}</>;
}
