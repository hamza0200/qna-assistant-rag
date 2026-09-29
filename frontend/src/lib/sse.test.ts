import { describe, expect, it } from "vitest";

import { parseFrame, readSSE, SSEParser } from "@/lib/sse";

function streamOf(chunks: (string | Uint8Array)[]): ReadableStream<Uint8Array> {
  const enc = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      for (const c of chunks) controller.enqueue(typeof c === "string" ? enc.encode(c) : c);
      controller.close();
    },
  });
}

async function collect(stream: ReadableStream<Uint8Array>) {
  const out = [];
  for await (const e of readSSE(stream)) out.push(e);
  return out;
}

describe("parseFrame", () => {
  it("reads event and data fields", () => {
    expect(parseFrame('event: token\ndata: {"text":"hi"}')).toEqual({
      event: "token",
      data: '{"text":"hi"}',
    });
  });

  it("defaults the event name to 'message'", () => {
    expect(parseFrame("data: x")).toEqual({ event: "message", data: "x" });
  });

  it("joins multi-line data with newlines and ignores comments", () => {
    expect(parseFrame(": keep-alive\nevent: e\ndata: a\ndata: b")).toEqual({ event: "e", data: "a\nb" });
  });

  it("returns null for frames without data", () => {
    expect(parseFrame(": just a comment")).toBeNull();
  });
});

describe("SSEParser", () => {
  it("handles events split across arbitrary chunk boundaries", () => {
    const p = new SSEParser();
    expect(p.push("event: tok")).toEqual([]);
    expect(p.push('en\ndata: {"text":"Hel')).toEqual([]);
    expect(p.push('lo"}\n')).toEqual([]);
    expect(p.push("\nevent: done\ndata: {}\n\n")).toEqual([
      { event: "token", data: '{"text":"Hello"}' },
      { event: "done", data: "{}" },
    ]);
  });

  it("normalizes CRLF line endings", () => {
    const p = new SSEParser();
    expect(p.push("event: a\r\ndata: 1\r\n\r\n")).toEqual([{ event: "a", data: "1" }]);
  });

  it("flushes a trailing event without a blank line", () => {
    const p = new SSEParser();
    expect(p.push("event: done\ndata: {}")).toEqual([]);
    expect(p.flush()).toEqual([{ event: "done", data: "{}" }]);
  });
});

describe("readSSE", () => {
  it("parses the chat event sequence from a byte stream", async () => {
    const body = [
      'event: meta\ndata: {"conversation_id":"c1","message_id":"m1"}\n\n',
      'event: token\ndata: {"text":"The price is "}\n\nevent: token\n',
      'data: {"text":"USD 29 [1]."}\n\n',
      'event: citations\ndata: [{"index":1,"filename":"guide.pdf","page":1}]\n\n',
      "event: done\ndata: {}\n\n",
    ];
    const events = await collect(streamOf(body));
    expect(events.map((e) => e.event)).toEqual(["meta", "token", "token", "citations", "done"]);
    const text = events
      .filter((e) => e.event === "token")
      .map((e) => JSON.parse(e.data).text)
      .join("");
    expect(text).toBe("The price is USD 29 [1].");
  });

  it("keeps multi-byte UTF-8 characters intact when split between chunks", async () => {
    const bytes = new TextEncoder().encode('event: token\ndata: {"text":"café · 29 €"}\n\n');
    const cut = bytes.indexOf(0xa9); // second byte of "é"
    const events = await collect(streamOf([bytes.slice(0, cut), bytes.slice(cut)]));
    expect(JSON.parse(events[0].data).text).toBe("café · 29 €");
  });
});
