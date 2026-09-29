"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { useAuth } from "@/lib/auth";

/** Entry point: send signed-in users to chat, everyone else to login. */
export default function Home() {
  const { ready, token } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (ready) router.replace(token ? "/chat" : "/login");
  }, [ready, token, router]);

  return <div className="grid min-h-dvh place-items-center text-sm text-muted">Loading…</div>;
}
