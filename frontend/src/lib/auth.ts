"use client";

// JWT storage: in memory for fast access + localStorage so a refresh keeps the
// session. Trade-off (see docs/DECISIONS.md): anything in localStorage is
// readable by injected script (XSS); production would use an httpOnly cookie.

import { useSyncExternalStore } from "react";

const STORAGE_KEY = "docmind.token";

let token: string | null = null;
let loaded = false;
const listeners = new Set<() => void>();

function load(): void {
  if (loaded || typeof window === "undefined") return;
  loaded = true;
  try {
    token = window.localStorage.getItem(STORAGE_KEY);
  } catch {
    token = null; // storage blocked (private mode etc.)
  }
}

function emit(): void {
  snapshot = { ready: true, token };
  listeners.forEach((l) => l());
}

export function getToken(): string | null {
  load();
  return token;
}

export function setToken(value: string): void {
  token = value;
  try {
    window.localStorage.setItem(STORAGE_KEY, value);
  } catch {
    /* keep the in-memory copy */
  }
  emit();
}

export function clearToken(): void {
  token = null;
  try {
    window.localStorage.removeItem(STORAGE_KEY);
  } catch {
    /* ignore */
  }
  emit();
}

// --- React binding -------------------------------------------------------
// `ready` is false during server rendering and hydration, so route guards don't
// redirect before the stored token has been read on the client.

interface AuthSnapshot {
  ready: boolean;
  token: string | null;
}

const SERVER_SNAPSHOT: AuthSnapshot = { ready: false, token: null };
let snapshot: AuthSnapshot | null = null;

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  // Keep tabs in sync: logging out in one tab logs out the others.
  const onStorage = (e: StorageEvent) => {
    if (e.key === STORAGE_KEY) {
      token = e.newValue;
      emit();
    }
  };
  window.addEventListener("storage", onStorage);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", onStorage);
  };
}

function getSnapshot(): AuthSnapshot {
  if (snapshot === null) {
    load();
    snapshot = { ready: true, token };
  }
  return snapshot;
}

export function useAuth(): AuthSnapshot {
  return useSyncExternalStore(subscribe, getSnapshot, () => SERVER_SNAPSHOT);
}
