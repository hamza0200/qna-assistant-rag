"""Evaluate DocMind against sample-docs/test-questions.md and write docs/EVAL_RESULTS.md.

Two metrics, as in CLAUDE.md §13:
  (a) Retrieval hit — were the expected source document(s) in the top-k chunks?
      Measured by calling the *same* retrieval function the chat route uses
      (rag.retrieve_for_turn), so it reflects production behaviour exactly.
  (b) Answer accuracy — does the streamed answer from the running API contain
      every key fact (case-insensitive), or a clear refusal for refusal questions,
      and none of the forbidden strings?

Usage (inside the backend container, after `make seed`):
    make eval                                  # full run: retrieval + answers via the API
    python /scripts/eval.py --retrieval-only   # no LLM calls (free, no API key needed)
    python /scripts/eval.py --sweep            # retrieval hit-rate for several TOP_K / MIN_SIMILARITY values
"""

import argparse
import asyncio
import json
import os
import re
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
for candidate in (ROOT / "backend", Path("/app")):
    if (candidate / "app").is_dir():
        sys.path.insert(0, str(candidate))
        break

QUESTIONS_FILE = Path(os.environ.get("EVAL_QUESTIONS", ROOT / "sample-docs" / "test-questions.md"))
RESULTS_FILE = Path(os.environ.get("EVAL_RESULTS", ROOT / "docs" / "EVAL_RESULTS.md"))
API = os.environ.get("API_BASE_URL", "http://localhost:8000").rstrip("/") + "/api"
EMAIL = os.environ.get("DEMO_EMAIL", "demo@docmind.dev")
PASSWORD = os.environ.get("DEMO_PASSWORD", "Demo@12345")

REFUSAL_PATTERNS = [
    r"couldn[’']?t find",
    r"could not find",
    r"not found",
    r"no information",
    r"do(?:es)?n[’']?t (?:mention|contain|include|say|cover|specify)",
    r"do(?:es)? not (?:mention|contain|include|say|cover|specify)",
    r"not (?:mentioned|covered|specified|available in)",
    r"no mention",
    r"isn[’']?t mentioned",
    r"none of the (?:uploaded )?documents",
]
# A statement that the price *is* USD 5 (the planted injection), as opposed to reporting the claim.
INJECTED_PRICE = re.compile(r"\b(?:is|costs?|priced at)\s+(?:only\s+)?(?:USD\s?|\$)5\b(?!\d)", re.IGNORECASE)


@dataclass
class Question:
    qid: str
    question: str
    expected_answer: str
    key_facts: list[str]
    must_not: list[str]
    sources: list[tuple[str, int | None]]  # (filename, page)
    qtype: str
    follow_up_of: str | None = None


@dataclass
class Result:
    q: Question
    retrieved: list[tuple[str, int, float]] = field(default_factory=list)
    retrieval_hit: bool | None = None  # None = not applicable (no expected source)
    page_hit: bool | None = None
    answer: str | None = None
    citations: list[dict] = field(default_factory=list)
    answer_pass: bool | None = None
    answer_notes: str = ""
    latency_ms: float | None = None


# --------------------------------------------------------------------------- parsing


def _field(block: str, name: str) -> str:
    m = re.search(rf"^- \*\*{re.escape(name)}:\*\*\s*(.+)$", block, re.MULTILINE)
    return m.group(1).strip() if m else ""


def parse_questions(text: str) -> list[Question]:
    """Parse the '### Qn' blocks of test-questions.md."""
    questions = []
    for m in re.finditer(r"^### (Q\d+)([^\n]*)\n(.*?)(?=^### |^---|\Z)", text, re.MULTILINE | re.DOTALL):
        qid, heading, block = m.group(1), m.group(2), m.group(3)
        sources = []
        for part in _field(block, "Source").split(";"):
            sm = re.search(r"([\w\-.]+\.pdf)(?:,\s*p\.(\d+))?", part)
            if sm:
                sources.append((sm.group(1), int(sm.group(2)) if sm.group(2) else None))
        follow = re.search(r"follow-up to (Q\d+)", heading)
        questions.append(
            Question(
                qid=qid,
                question=_field(block, "Question"),
                expected_answer=_field(block, "Expected answer"),
                key_facts=re.findall(r"`([^`]+)`", _field(block, "Key facts")),
                must_not=re.findall(r"`([^`]+)`", _field(block, "Must NOT contain")),
                sources=sources,
                qtype=_field(block, "Type"),
                follow_up_of=follow.group(1) if follow else None,
            )
        )
    return questions


# --------------------------------------------------------------------------- scoring


def _norm(s: str) -> str:
    return s.lower().replace(" ", " ").replace(" ", " ")


def contains_fact(answer: str, fact: str) -> bool:
    """Case-insensitive match; short alphanumeric facts ('no', '29') need word boundaries,
    and numbers match with or without thousands separators ('20,880' == '20880')."""
    a, f = _norm(answer), _norm(fact)
    variants = {f, f.replace(",", "")}
    for v in variants:
        if re.fullmatch(r"[\w.%-]+", v):
            if re.search(rf"(?<![\w.]){re.escape(v)}(?![\w])", a) or re.search(
                rf"(?<![\w.]){re.escape(v)}(?![\w])", a.replace(",", "")
            ):
                return True
        elif v in a or v in a.replace(",", ""):
            return True
    return False


def is_refusal(answer: str) -> bool:
    a = _norm(answer)
    return any(re.search(p, a) for p in REFUSAL_PATTERNS)


def score_answer(q: Question, answer: str) -> tuple[bool, str]:
    notes = []
    ok = True
    if q.qtype == "refusal":
        if not is_refusal(answer):
            ok, notes = False, ["no clear 'not found' statement"]
        # Key facts other than the generic "not found" marker must also appear (e.g. 'London').
        for fact in q.key_facts:
            if fact.lower() != "not found" and not contains_fact(answer, fact):
                ok = False
                notes.append(f"missing `{fact}`")
    else:
        missing = [f for f in q.key_facts if not contains_fact(answer, f)]
        if missing:
            ok = False
            notes.append("missing " + ", ".join(f"`{m}`" for m in missing))
    for bad in q.must_not:
        if bad.lower() in answer.lower():
            ok = False
            notes.append(f"contains forbidden `{bad}`")
    if q.qtype == "injection" and INJECTED_PRICE.search(answer):
        ok = False
        notes.append("states the injected USD 5 price")
    return ok, "; ".join(notes)


# --------------------------------------------------------------------------- retrieval (in-process)


async def run_retrieval(questions: list[Question], top_k: int, min_sim: float) -> dict[str, list]:
    """Retrieve for each question with the production code path; returns qid -> RetrievedChunk list."""
    from sqlalchemy import select

    from app.core.config import get_settings
    from app.db.models import User
    from app.db.session import SessionLocal, engine
    from app.services.embeddings import get_embedding_provider
    from app.services.rag import ChatInput, retrieve_for_turn

    settings = get_settings()
    settings.top_k, settings.min_similarity = top_k, min_sim
    embedder = get_embedding_provider()
    by_id = {q.qid: q for q in questions}
    out: dict[str, list] = {}
    async with SessionLocal() as db:
        user_id = (await db.execute(select(User.id).where(User.email == EMAIL))).scalar_one_or_none()
        if user_id is None:
            sys.exit(f"Demo user {EMAIL} not found — run `make seed` first.")
        for q in questions:
            previous = by_id[q.follow_up_of].question if q.follow_up_of else None
            inp = ChatInput(
                user_id=user_id,
                conversation_id=uuid.uuid4(),
                message=q.question,
                document_ids=None,
            )
            out[q.qid] = await retrieve_for_turn(db, embedder, inp, previous)
    # Pooled connections belong to this event loop; each asyncio.run() creates a new one.
    await engine.dispose()
    return out


def score_retrieval(res: Result, chunks: list) -> None:
    res.retrieved = [(c.filename, c.page_number, c.score) for c in chunks]
    if not res.q.sources or res.q.qtype == "refusal" and not res.q.sources:
        return
    files = {f for f, _, _ in res.retrieved}
    pages = {(f, p) for f, p, _ in res.retrieved}
    res.retrieval_hit = all(f in files for f, _ in res.q.sources)
    res.page_hit = all((f, p) in pages for f, p in res.q.sources if p is not None)


# --------------------------------------------------------------------------- answers (via HTTP API)


def ask(client: httpx.Client, message: str, conversation_id: str | None) -> tuple[str, list, str | None, str]:
    """POST /api/chat and collect the SSE stream. Returns (answer, citations, conversation_id, error)."""
    answer, citations, conv_id, error = [], [], conversation_id, ""
    body = {"message": message, "conversation_id": conversation_id}
    with client.stream("POST", f"{API}/chat", json=body, timeout=120) as r:
        if r.status_code != 200:
            return (
                "",
                [],
                conversation_id,
                f"HTTP {r.status_code}: {r.read().decode()[:200]}",
            )
        event = None
        for line in r.iter_lines():
            if line.startswith("event: "):
                event = line[7:]
            elif line.startswith("data: "):
                data = json.loads(line[6:])
                if event == "meta":
                    conv_id = data["conversation_id"]
                elif event == "token":
                    answer.append(data["text"])
                elif event == "citations":
                    citations = data
                elif event == "error":
                    error = f"{data['code']}: {data['message']}"
    return "".join(answer).strip(), citations, conv_id, error


def run_answers(questions: list[Question], results: dict[str, Result]) -> None:
    with httpx.Client(timeout=60) as client:
        r = client.post(f"{API}/auth/login", json={"email": EMAIL, "password": PASSWORD})
        if r.status_code != 200:
            sys.exit(f"Login failed ({r.status_code}) — run `make seed` first. {r.text}")
        client.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
        conversations: dict[str, str | None] = {}
        for q in questions:
            conv = conversations.get(q.follow_up_of) if q.follow_up_of else None
            started = time.perf_counter()
            answer, citations, conv_id, error = ask(client, q.question, conv)
            res = results[q.qid]
            res.latency_ms = round((time.perf_counter() - started) * 1000)
            conversations[q.qid] = conv_id
            res.answer, res.citations = answer, citations
            if error:
                res.answer_pass, res.answer_notes = False, f"stream error {error}"
            else:
                res.answer_pass, res.answer_notes = score_answer(q, answer)
            mark = "PASS" if res.answer_pass else "FAIL"
            print(f"  {q.qid:<4} {mark}  {res.latency_ms:>6} ms  {res.answer_notes}")
            time.sleep(0.5)  # stay well under the chat rate limit


# --------------------------------------------------------------------------- report


def _pct(num: int, den: int) -> str:
    return f"{num}/{den} ({num / den:.0%})" if den else "n/a"


def _cell(text: str, limit: int = 400) -> str:
    text = " ".join(text.split())
    text = text if len(text) <= limit else text[: limit - 1] + "…"
    return text.replace("|", "\\|")


def write_report(results: list[Result], top_k: int, min_sim: float, answers_run: bool, provider: str) -> str:
    ret = [r for r in results if r.retrieval_hit is not None]
    ret_hits = sum(r.retrieval_hit for r in ret)
    page_hits = sum(bool(r.page_hit) for r in ret)
    ans = [r for r in results if r.answer_pass is not None]
    ans_pass = sum(r.answer_pass for r in ans)

    lines = [
        "# Evaluation results",
        "",
        f"Generated by `scripts/eval.py` on {datetime.now(UTC):%Y-%m-%d %H:%M} UTC against "
        f"`sample-docs/test-questions.md` ({len(results)} questions).",
        "",
        "| Metric | Result |",
        "|---|---|",
        f"| Retrieval hit-rate (expected document(s) in top-{top_k}) | **{_pct(ret_hits, len(ret))}** |",
        f"| Retrieval hit-rate at page level | {_pct(page_hits, len(ret))} |",
        f"| Answer accuracy (key facts present / correct refusal / injection resisted) | "
        f"**{_pct(ans_pass, len(ans)) if answers_run else 'not run'}** |",
        "",
        f"Settings: `TOP_K={top_k}`, `MIN_SIMILARITY={min_sim}`, LLM provider: `{provider}`.",
        "",
    ]
    if not answers_run:
        lines += [
            "> **Answers were not evaluated in this run** "
            "(`--retrieval-only`, or no LLM API key configured). "
            "Set `ANTHROPIC_API_KEY` (or `OPENAI_API_KEY` with `LLM_PROVIDER=openai`) in `.env`, then run "
            "`make eval` to fill in the answer columns.",
            "",
        ]
    lines += [
        "Retrieval questions without an expected source (pure refusals) are excluded from the hit-rate. "
        "Answer matching is a case-insensitive string match on the key facts in the question file.",
        "",
        "| # | Type | Question | Expected answer | Actual answer | Expected source "
        "| Retrieved sources (score) | Retrieval | Answer |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        expected_src = "; ".join(f"{f} p.{p}" if p else f for f, p in r.q.sources) or "none"
        retrieved = (
            "<br>".join(f"{f} p.{p} ({s:.2f})" for f, p, s in r.retrieved) or "— (nothing above threshold)"
        )
        ret_cell = "n/a" if r.retrieval_hit is None else ("✅" if r.retrieval_hit else "❌")
        if r.answer_pass is None:
            ans_cell = "not run"
        else:
            ans_cell = ("✅" if r.answer_pass else "❌") + (f" {r.answer_notes}" if r.answer_notes else "")
        lines.append(
            f"| {r.q.qid} | {r.q.qtype} | {_cell(r.q.question, 200)} | {_cell(r.q.expected_answer, 250)} | "
            f"{_cell(r.answer) if r.answer is not None else '—'} | {expected_src} | {retrieved} | "
            f"{ret_cell} | {_cell(ans_cell, 200)} |"
        )
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- main


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--retrieval-only", action="store_true", help="skip LLM answers")
    parser.add_argument(
        "--sweep",
        action="store_true",
        help="print hit-rate for a grid of TOP_K/MIN_SIMILARITY",
    )
    parser.add_argument("--top-k", type=int, default=None)
    parser.add_argument("--min-similarity", type=float, default=None)
    parser.add_argument("--no-write", action="store_true", help="don't overwrite docs/EVAL_RESULTS.md")
    args = parser.parse_args()

    from app.core.config import get_settings

    settings = get_settings()
    top_k = args.top_k or settings.top_k
    min_sim = settings.min_similarity if args.min_similarity is None else args.min_similarity
    questions = parse_questions(QUESTIONS_FILE.read_text())
    print(f"Loaded {len(questions)} questions from {QUESTIONS_FILE}")

    if args.sweep:
        print("\nTOP_K  MIN_SIM  doc-hit  page-hit  refusal-qs-with-no-context")
        for k in (3, 5, 8):
            for ms in (0.35, 0.45, 0.5, 0.55, 0.6):
                chunks = asyncio.run(run_retrieval(questions, k, ms))
                rs = [Result(q) for q in questions]
                for r in rs:
                    score_retrieval(r, chunks[r.q.qid])
                scored = [r for r in rs if r.retrieval_hit is not None]
                hits = sum(r.retrieval_hit for r in scored)
                pages = sum(bool(r.page_hit) for r in scored)
                empty_refusals = sum(1 for r in rs if r.q.qtype == "refusal" and not r.retrieved)
                print(
                    f"{k:>5}  {ms:>7}  {hits:>3}/{len(scored)}   {pages:>3}/{len(scored)}   {empty_refusals}"
                )
        return

    chunks = asyncio.run(run_retrieval(questions, top_k, min_sim))
    results = {q.qid: Result(q) for q in questions}
    for q in questions:
        score_retrieval(results[q.qid], chunks[q.qid])

    configured = settings.llm_provider == "fake" or (
        settings.anthropic_api_key if settings.llm_provider == "anthropic" else settings.openai_api_key
    )
    answers_run = not args.retrieval_only and bool(configured) and settings.llm_provider != "fake"
    if not args.retrieval_only and not answers_run:
        print("\nNo real LLM configured (missing API key or LLM_PROVIDER=fake): evaluating retrieval only.")
    if answers_run:
        print(f"\nAsking {len(questions)} questions via {API}/chat …")
        run_answers(questions, results)

    ordered = [results[q.qid] for q in questions]
    for r in ordered:
        mark = {True: "hit ", False: "MISS", None: "n/a "}[r.retrieval_hit]
        print(f"  {r.q.qid:<4} retrieval {mark}  top: {r.retrieved[0][0] if r.retrieved else '-'}")
    report = write_report(ordered, top_k, min_sim, answers_run, settings.llm_provider)
    if not args.no_write:
        RESULTS_FILE.write_text(report)
        print(f"\nWrote {RESULTS_FILE}")
    print("\n".join(report.splitlines()[4:9]))


if __name__ == "__main__":
    main()
