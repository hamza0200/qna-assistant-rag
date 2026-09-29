# 7. Frontend

## React fundamentals

- **Components** are functions of props and state that return UI. React re-renders a component when its state changes, its parent re-renders, or a context it uses changes.
- **State (`useState`)** holds data that changes over time; updates are *scheduled*, not immediate. When the next value depends on the previous one, use the updater form: `setMessages(prev => [...prev, msg])` — essential while tokens stream in quickly.
- **Effects (`useEffect`)** synchronize with things outside React (fetching, timers, event listeners). Return a cleanup function; list every dependency. DocMind's polling effect starts an interval only while documents are processing and clears it on cleanup (`frontend/src/app/documents/page.tsx`).
- **Keys** tell React which list item is which across renders. Use stable IDs (`message.id`), never array indexes for lists that change — otherwise state/DOM gets attached to the wrong item.
- **Memoization:** `memo(Component)` skips re-rendering when props are unchanged; `useCallback`/`useMemo` keep function/object identities stable so memo works. DocMind memoizes `MessageBubble` so earlier messages don't re-render on every streamed token, and passes stable callbacks (`openCitation` via `useCallback`).
- **Refs (`useRef`)** hold mutable values that don't trigger renders — the `AbortController`, the scroll container, "was this conversation created by the current stream?".

### A real bug from this project: stale closures

State updaters run *later*, at render time. This code captured a mutable variable:

```ts
setMessages(prev => prev.map(m => m.id === assistantId ? {...m, id: serverId} : m));
assistantId = serverId;   // reassigned before the updater ran!
```

By the time React ran the updater, `assistantId` already held the new value, so nothing matched and every streamed token went nowhere. Fix: copy into a `const` first (`const localId = assistantId`). Found by an end-to-end browser test, not a unit test.

## Next.js App Router

- **File-system routing:** `src/app/chat/page.tsx` → `/chat`; `(auth)` is a **route group** — organizes files without adding a URL segment (`/login`, not `/auth/login`); `layout.tsx` wraps children and persists across navigation.
- **Server vs client components:** components are **server components** by default — rendered on the server, zero JS shipped, can read databases/secrets directly. Add `"use client"` for interactivity (state, effects, browser APIs, event handlers). DocMind's layout is a server component; the pages that use the token, streaming and drag-and-drop are client components.
- **Rendering modes:**
  - **SSG** (static, at build time) — DocMind's routes are prerendered static shells (`○ (Static)` in the build output).
  - **SSR** (per request on the server) — for personalized pages when the server can identify the user (cookies).
  - **CSR** (in the browser) — DocMind fetches user data client-side because the JWT lives in the browser.
  - **ISR / revalidation** — static pages regenerated periodically or on demand.
- **Caching:** Next caches fetches, rendered routes and client-side router segments; invalidate with `revalidatePath`/`revalidateTag`/`updateTag`. Most caching is irrelevant to DocMind since data is fetched client-side.
- **Next.js 16 specifics:** `middleware.ts` is renamed `proxy.ts`; request APIs (`params`, `searchParams`, `cookies()`, `headers()`) are async only; Turbopack is the default bundler; `useSearchParams` must sit under a `<Suspense>` boundary on prerendered routes (DocMind's `chat/page.tsx` does this).
- **`NEXT_PUBLIC_*`** variables are inlined into the browser bundle at build time — never put secrets there; changing them needs a rebuild.

## TypeScript essentials

- **`strict: true`** (DocMind's `tsconfig.json`): no implicit `any`, strict null checks — `document.find(...)` returns `T | undefined` and you must handle it.
- **Generics:** `apiFetch<T>(path): Promise<T>` in `frontend/src/lib/api.ts` — one function, typed results (`api.listDocuments()` returns `Promise<DocumentOut[]>`).
- **Utility types:** `Partial<T>`, `Pick<T, K>`, `Omit<T, K>`, `Record<K, V>` (DocMind's `STATUS: Record<DocumentStatus, …>` forces a style for every status), `ReturnType<typeof fn>`.
- **Narrowing:** `typeof`, `instanceof` (`err instanceof ApiError`), `in`, and **discriminated unions** — the SSE events are typed as a union keyed on `event`, so inside `case "citations":` TypeScript knows `data` is `Citation[]`:

```ts
export type ChatStreamEvent =
  | { event: "meta"; data: { conversation_id: string; message_id: string } }
  | { event: "token"; data: { text: string } }
  | { event: "citations"; data: Citation[] }
  | { event: "error"; data: { code: string; message: string } }
  | { event: "done"; data: Record<string, never> };
```

- **`unknown` over `any`** for untrusted data (catch clauses, JSON): forces a check before use.

## Consuming streams with ReadableStream

`fetch` exposes the response body as a `ReadableStream<Uint8Array>`. DocMind's reader (`frontend/src/lib/sse.ts`):

```ts
const reader = body.getReader();
const decoder = new TextDecoder();
const parser = new SSEParser();
while (true) {
  const { done, value } = await reader.read();
  if (done) break;
  yield* parser.push(decoder.decode(value, { stream: true }));
}
```

Two subtleties covered by tests (`src/lib/sse.test.ts`): network chunks don't align with events, so the parser buffers until a blank line; and a multi-byte UTF-8 character can be split across chunks, so `TextDecoder` must use `{ stream: true }`.

## AbortController

```ts
const controller = new AbortController();
fetch(url, { signal: controller.signal });
controller.abort();   // Stop button
```

Aborting rejects the pending `fetch`/`read()` with an `AbortError` (DocMind marks the message "Stopped") and closes the connection; the server notices the disconnect, cancels the LLM stream (no more tokens billed) and saves the partial answer. Also use it to cancel stale requests when a component unmounts or the user navigates.

## State management choices

DocMind uses **local state + custom hooks** (`useChatStream`) and a tiny external store for the token (`useSyncExternalStore` in `frontend/src/lib/auth.ts`). Options as apps grow:

| Tool | Use for |
|---|---|
| `useState` / `useReducer` / custom hooks | component and feature state (most state) |
| Context | low-frequency global values (theme, current user) — every consumer re-renders on change |
| Zustand / Redux Toolkit / Jotai | shared client state with frequent updates and selectors |
| TanStack Query / SWR | **server state**: caching, deduping, background refetch, polling, retries — would replace DocMind's manual polling and loading flags |

`useSyncExternalStore` also solves a hydration problem: the server can't read localStorage, so the auth store returns a "not ready" server snapshot and route guards wait until the client snapshot is available.

## Performance

- **Code splitting:** Next splits per route automatically; `next/dynamic` / `React.lazy` for heavy components used rarely.
- **Avoid unnecessary re-renders:** keep state as local as possible, memoize list items, stable callbacks, don't create new objects/arrays in props every render, virtualize long lists (`react-window`).
- **Network:** stream responses (perceived latency = time to first token), prefetch routes (Next `Link` does), cache server state.
- **Assets:** `next/font` self-hosts fonts (no layout shift, no runtime request); `next/image` for responsive images.
- **Measure:** React DevTools Profiler, Lighthouse, Core Web Vitals (LCP, INP, CLS).

## Accessibility basics

What DocMind does: labelled inputs (`<label htmlFor>`), visible focus rings (`:focus-visible`), keyboard submit (Enter; Shift+Enter newline; IME composition respected), `role="alert"` for errors and the toast, `aria-live` for "Searching your documents…", `aria-pressed`/`aria-expanded`/`aria-current` on toggles and navigation, `role="group"` + `aria-label` on the citation chips (caught by a Testing Library role query), a `progressbar` role on upload progress, and `prefers-reduced-motion` support. Principles to name: semantic HTML first, keyboard operability, sufficient contrast, text alternatives, don't rely on color alone (status badges have text).
