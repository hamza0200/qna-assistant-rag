import type { Citation } from "@/types";

interface CitationChipProps {
  citation: Citation;
  active?: boolean;
  onOpen: (citation: Citation) => void;
}

/** `[1] Orbitra_Vault_Product_Guide.pdf · p.3` — opens the cited passage in the source panel. */
export function CitationChip({ citation, active = false, onOpen }: CitationChipProps) {
  return (
    <button
      type="button"
      onClick={() => onOpen(citation)}
      title={citation.snippet}
      aria-pressed={active}
      className={`inline-flex max-w-full items-center gap-1.5 rounded-md border px-2 py-1 text-left text-xs transition-colors ${
        active ? "border-ink/40 bg-marker-soft" : "border-line bg-surface hover:border-muted"
      }`}
    >
      <span className="rounded-sm bg-marker px-1 font-semibold text-ink">{citation.index}</span>
      <span className="truncate">{citation.filename}</span>
      <span className="shrink-0 text-muted">· p.{citation.page}</span>
    </button>
  );
}
