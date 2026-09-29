import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { linkCitations, MessageBubble } from "@/components/MessageBubble";
import type { ChatMessage } from "@/hooks/useChatStream";
import type { Citation } from "@/types";

afterEach(cleanup);

const citation: Citation = {
  index: 1,
  chunk_id: "chunk-1",
  document_id: "doc-1",
  filename: "Orbitra_Vault_Product_Guide.pdf",
  page: 3,
  score: 0.82,
  snippet: "The Business plan costs USD 29…",
};

function message(overrides: Partial<ChatMessage> = {}): ChatMessage {
  return {
    id: "m1",
    role: "assistant",
    content: "It costs **USD 29** per user [1].",
    citations: [citation],
    status: "done",
    ...overrides,
  };
}

describe("linkCitations", () => {
  it("turns [n] markers into citation links but leaves real Markdown links alone", () => {
    expect(linkCitations("See [1] and [2][3].")).toBe("See [1](#cite-1) and [2](#cite-2)[3](#cite-3).");
    expect(linkCitations("[docs](https://x.y)")).toBe("[docs](https://x.y)");
  });
});

describe("MessageBubble", () => {
  it("renders Markdown and a citation chip that opens the source", () => {
    const onOpen = vi.fn();
    render(<MessageBubble message={message()} activeChunkId={null} onOpenCitation={onOpen} />);

    expect(screen.getByText("USD 29").tagName).toBe("STRONG");
    const sources = screen.getByRole("group", { name: "Sources" });
    const chip = within(sources).getByRole("button", { name: /Orbitra_Vault_Product_Guide\.pdf/ });
    expect(chip.textContent).toContain("p.3");
    fireEvent.click(chip);
    expect(onOpen).toHaveBeenCalledWith(citation);

    // The inline [1] marker is clickable too.
    fireEvent.click(
      screen.getByRole("button", { name: "Source 1: Orbitra_Vault_Product_Guide.pdf, page 3" }),
    );
    expect(onOpen).toHaveBeenCalledTimes(2);
  });

  it("does not render HTML from model output", () => {
    const { container } = render(
      <MessageBubble
        message={message({ content: '<img src=x onerror="alert(1)"> hello', citations: [] })}
        activeChunkId={null}
        onOpenCitation={() => {}}
      />,
    );
    expect(container.querySelector("img")).toBeNull();
  });

  it("shows a stopped note", () => {
    render(
      <MessageBubble
        message={message({ status: "stopped" })}
        activeChunkId={null}
        onOpenCitation={() => {}}
      />,
    );
    expect(screen.getByText("Stopped.")).toBeTruthy();
  });
});
