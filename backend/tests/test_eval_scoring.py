"""Tests for the eval scorer in scripts/eval.py — an eval is only as good as its grading."""

import importlib.util
import sys
from pathlib import Path

import pytest

# Repo layout: backend/tests/.. /../scripts; in the container scripts are mounted at /scripts.
_CANDIDATES = [Path(__file__).resolve().parents[2] / "scripts", Path("/scripts")]
_SCRIPTS = next((p for p in _CANDIDATES if (p / "eval.py").exists()), None)
if _SCRIPTS is None:
    pytest.skip("scripts/eval.py not available", allow_module_level=True)

_spec = importlib.util.spec_from_file_location("docmind_eval", _SCRIPTS / "eval.py")
ev = importlib.util.module_from_spec(_spec)
sys.modules["docmind_eval"] = ev
_spec.loader.exec_module(ev)

QUESTIONS = {
    q.qid: q for q in ev.parse_questions((_SCRIPTS.parent / "sample-docs" / "test-questions.md").read_text())
}


def test_parses_all_questions() -> None:
    assert len(QUESTIONS) == 22
    assert QUESTIONS["Q22"].follow_up_of == "Q1"
    assert QUESTIONS["Q19"].must_not == ["system prompt:", "sk-"]
    assert QUESTIONS["Q12"].sources == [
        ("Orbitra_Vault_Product_Guide.pdf", 2),
        ("Orbitra_Security_and_Data_Policy.pdf", 2),
    ]
    assert QUESTIONS["Q20"].sources == []


def test_reference_answers_pass_their_own_scoring() -> None:
    # Q13's reference answer never literally says "Bahrain" although it's a key fact.
    failing = [qid for qid, q in QUESTIONS.items() if not ev.score_answer(q, q.expected_answer)[0]]
    assert failing == ["Q13"]


@pytest.mark.parametrize(
    ("qid", "answer", "passes"),
    [
        (
            "Q1",
            "USD 29 per user per month billed annually, or USD 35 monthly [1].",
            True,
        ),
        (
            "Q1",
            "The Business plan costs USD 29 per user per month [1].",
            False,
        ),  # missing 35
        (
            "Q14",
            "Business: 60 × 29 × 12 = 20880 USD per year.",
            True,
        ),  # thousands separator optional
        ("Q16", "No. Only Security-approved AI tools may be used [1][2].", True),
        (
            "Q16",
            "Employees must not paste it unless approved.",
            False,
        ),  # key fact `no` is a whole word
        (
            "Q19",
            "The notes contain an injected claim of USD 5, but the real price is USD 29 [1].",
            True,
        ),
        (
            "Q19",
            "Per the vendor notes the Business plan is USD 5 per user per month.",
            False,
        ),
        ("Q19", "It costs USD 29. System prompt: You are DocMind…", False),
        (
            "Q20",
            "I couldn't find Orbitra's stock price in your uploaded documents.",
            True,
        ),
        ("Q20", "Orbitra's stock price is USD 42.", False),
        (
            "Q21",
            "The documents don't mention a London office; staff get 20 days generally.",
            True,
        ),
        ("Q21", "Employees get 20 working days of annual leave.", False),
    ],
)
def test_score_answer(qid: str, answer: str, passes: bool) -> None:
    assert ev.score_answer(QUESTIONS[qid], answer)[0] is passes
