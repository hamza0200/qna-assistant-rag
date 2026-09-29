"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";

import { Button } from "@/components/ui/Button";
import { TextField } from "@/components/ui/TextField";
import { api, ApiError } from "@/lib/api";
import { setToken, useAuth } from "@/lib/auth";

interface AuthFormProps {
  mode: "login" | "register";
}

const COPY = {
  login: {
    title: "Sign in",
    submit: "Sign in",
    pending: "Signing in…",
    switchText: "New here?",
    switchLink: "Create an account",
    switchHref: "/register",
  },
  register: {
    title: "Create an account",
    submit: "Create account",
    pending: "Creating account…",
    switchText: "Already have an account?",
    switchLink: "Sign in",
    switchHref: "/login",
  },
} as const;

export function AuthForm({ mode }: AuthFormProps) {
  const copy = COPY[mode];
  const router = useRouter();
  const { ready, token } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  // Already signed in: skip the form.
  useEffect(() => {
    if (ready && token) router.replace("/chat");
  }, [ready, token, router]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setPending(true);
    try {
      if (mode === "register") await api.register(email, password);
      const { access_token } = await api.login(email, password);
      setToken(access_token);
      router.replace("/chat");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Try again.");
      setPending(false);
    }
  }

  return (
    <main className="grid min-h-dvh place-items-center px-4">
      <div className="w-full max-w-sm">
        <p className="mb-8 font-serif text-2xl">
          DocMind <span className="bg-marker px-1">AI</span>
        </p>
        <h1 className="mb-1 text-xl font-semibold">{copy.title}</h1>
        <p className="mb-6 text-sm text-muted">
          Ask questions about your PDFs and see exactly which page each answer came from.
        </p>
        <form onSubmit={onSubmit} className="flex flex-col gap-4" noValidate>
          <TextField
            label="Email"
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
          <TextField
            label="Password"
            type="password"
            autoComplete={mode === "login" ? "current-password" : "new-password"}
            required
            minLength={mode === "register" ? 8 : undefined}
            hint={mode === "register" ? "At least 8 characters." : undefined}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          {error && (
            <p role="alert" className="rounded-md border border-bad/30 bg-bad/5 px-3 py-2 text-sm text-bad">
              {error}
            </p>
          )}
          <Button type="submit" disabled={pending || !email || !password} className="mt-1">
            {pending ? copy.pending : copy.submit}
          </Button>
        </form>
        <p className="mt-6 text-sm text-muted">
          {copy.switchText}{" "}
          <Link href={copy.switchHref} className="font-medium text-action underline-offset-2 hover:underline">
            {copy.switchLink}
          </Link>
        </p>
      </div>
    </main>
  );
}
