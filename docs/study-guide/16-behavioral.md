# 16. Behavioural questions

Use **STAR**: **S**ituation (one or two sentences of context), **T**ask (what *you* were responsible for), **A**ction (what *you* did — most of the answer, with specifics), **R**esult (measurable outcome + what you learned). Aim for ~2 minutes. Prepare 5–6 real stories you can adapt; each template below has prompts to fill with your own experience. Where DocMind gives you a genuine example, it's noted — use it only as far as it's true for you.

## 1. Tell me about a conflict with a teammate.

- **S:** Project, teammate's role, what you disagreed about (technical approach, ownership, quality bar).
- **T:** What outcome you were responsible for.
- **A:** How you understood their view first (1:1, asked questions), found shared goals, used data or a small experiment to decide, agreed on a path, followed up.
- **R:** What was shipped, how the relationship ended up, what you do differently now.
- *Signal they want:* you disagree respectfully, decide with evidence, and commit.

## 2. Tell me about a failure.

- **S/T:** Something you owned that went wrong (missed estimate, bug in production, wrong design).
- **A:** How you noticed, owned it without blame, fixed the immediate problem, and fixed the cause (test, process, alert).
- **R:** Impact contained, the lasting change you introduced.
- *DocMind-flavoured example:* a streaming bug where answers stayed blank because a React state updater read a variable reassigned before it ran — unit tests passed; an end-to-end browser test caught it. Lesson: test the real flow, not just the pieces.

## 3. Tell me about working to a tight deadline.

- **S/T:** Deadline, scope, constraints.
- **A:** How you cut scope deliberately (must-haves vs nice-to-haves), communicated trade-offs early, sequenced work to have something shippable at each step, protected quality on the critical path.
- **R:** Delivered what, when; what you deferred and how you tracked it.
- *DocMind-flavoured example:* building a full RAG app in phases with a working, committed checkpoint at each phase, and recording deferred items (hybrid search, queue, cookies) as explicit decisions rather than dropping them silently.

## 4. Tell me about disagreeing with a product manager.

- **S:** A feature/timeline/requirement you thought was wrong (risky, costly, unclear value).
- **T:** Your role in the decision.
- **A:** Framed it in terms of user/business impact, not preference; brought data or a prototype; proposed alternatives (smaller scope, phased rollout, experiment); accepted the final call.
- **R:** Outcome and relationship; what you'd repeat.

## 5. Tell me about mentoring someone.

- **S/T:** Who, what they needed (onboarding, a skill, confidence).
- **A:** Pairing, reviews with explanations rather than fixes, gradually larger tasks, regular check-ins, creating docs they could reuse.
- **R:** Their growth (shipped X independently), and what you learned about teaching.

## 6. Tell me about a production incident you handled.

- **S:** What broke, user impact, how it was detected.
- **T:** Your role (on call, incident lead, fixer).
- **A:** Stabilize first (rollback/feature flag/scale), communicate status, find the root cause with logs/metrics/traces, fix, then a blameless post-mortem with action items.
- **R:** Time to mitigation, follow-ups (alerts, tests, runbooks) that prevented recurrence.
- *Talking point from DocMind:* structured logs with request IDs and per-turn LLM metrics exist precisely so an incident can be traced from a user's report to the failing step.

## 7. Tell me about a time you learned something new quickly.

- **S/T:** A technology/domain you had to pick up fast.
- **A:** How you learned: official docs, a small spike, building the smallest end-to-end slice, asking experts, writing notes.
- **R:** What you delivered with it.
- *DocMind-flavoured example:* verifying current library behaviour instead of relying on memory — e.g. reading the installed Next.js 16 docs (middleware renamed to proxy, async request APIs) and the current Anthropic SDK before writing code.

## 8. Tell me about a technical decision you made and its trade-offs.

- **S/T:** The decision and constraints.
- **A:** Options you considered, how you evaluated them (criteria, measurements), why you chose one, how you documented it.
- **R:** How it played out; when you'd revisit it.
- *DocMind-flavoured example:* choosing the similarity threshold by measurement (0.45, after finding answerable and off-topic score ranges overlap) and documenting it as an ADR.

## 9. Tell me about improving code quality or a process.

- **S/T:** A pain point (flaky tests, slow CI, bugs from missing checks).
- **A:** What you changed (tests, linters, CI steps, review checklist), how you got buy-in.
- **R:** Measured improvement (CI time, bug rate, review time).
- *DocMind-flavoured example:* making the test suite 8× faster (20 s → 2.5 s) by making the bcrypt cost configurable and using the minimum in tests only.

## 10. Why this role / why us?

- Connect three things: what the company builds, what you've demonstrated (full-stack + AI features, shipped end to end, security-minded, measured quality), and what you want to grow in. Be specific about the product; mention one thing you'd be excited to work on in the first months.

## Questions to ask them

- How do you evaluate AI features before and after release?
- What does the path from prototype to production look like for an AI feature here?
- How are on-call and incidents handled? What does a good first 90 days look like?
- What's the biggest technical challenge the team faces this year?
