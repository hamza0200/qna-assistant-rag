// Incremental Server-Sent Events parser.
//
// We can't use the browser's EventSource: it only supports GET and can't send an
// Authorization header. Instead we POST with fetch() and parse the byte stream
// ourselves. Network chunks don't align with event boundaries, so the parser
// buffers partial input and only emits complete events (terminated by a blank line).

export interface RawSSEEvent {
  event: string;
  data: string;
}

export class SSEParser {
  private buffer = "";

  /** Feed a decoded text chunk; returns every event completed by it. */
  push(chunk: string): RawSSEEvent[] {
    this.buffer += chunk.replace(/\r\n?/g, "\n");
    const events: RawSSEEvent[] = [];
    let boundary = this.buffer.indexOf("\n\n");
    while (boundary !== -1) {
      const frame = this.buffer.slice(0, boundary);
      this.buffer = this.buffer.slice(boundary + 2);
      const parsed = parseFrame(frame);
      if (parsed) events.push(parsed);
      boundary = this.buffer.indexOf("\n\n");
    }
    return events;
  }

  /** Flush a final event that wasn't followed by a blank line (stream ended). */
  flush(): RawSSEEvent[] {
    const rest = this.buffer.trim();
    this.buffer = "";
    const parsed = rest ? parseFrame(rest) : null;
    return parsed ? [parsed] : [];
  }
}

/** Parse one frame per the SSE spec: `field: value` lines, `:` comments, multi-line data. */
export function parseFrame(frame: string): RawSSEEvent | null {
  let event = "message";
  const data: string[] = [];
  for (const line of frame.split("\n")) {
    if (line === "" || line.startsWith(":")) continue; // comment / keep-alive
    const colon = line.indexOf(":");
    const field = colon === -1 ? line : line.slice(0, colon);
    let value = colon === -1 ? "" : line.slice(colon + 1);
    if (value.startsWith(" ")) value = value.slice(1);
    if (field === "event") event = value;
    else if (field === "data") data.push(value);
  }
  if (data.length === 0) return null;
  return { event, data: data.join("\n") };
}

/** Read a fetch() Response body as SSE events. */
export async function* readSSE(body: ReadableStream<Uint8Array>): AsyncGenerator<RawSSEEvent> {
  const reader = body.getReader();
  // stream: true keeps multi-byte UTF-8 characters split across chunks intact.
  const decoder = new TextDecoder();
  const parser = new SSEParser();
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      yield* parser.push(decoder.decode(value, { stream: true }));
    }
    yield* parser.push(decoder.decode());
    yield* parser.flush();
  } finally {
    reader.releaseLock();
  }
}
