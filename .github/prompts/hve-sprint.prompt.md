---
description: "Run a full HVE sprint loop (Research → Plan → Implement → Review) on a single task. Use as a one-shot orchestration when you want a complete delivery cycle in one chat."
mode: agent
---

# HVE Sprint — One Task, Four Phases

You are orchestrating the Arup Smart Bid **Hypervelocity Engineering (HVE)** workflow for the task below. Drive the full loop end-to-end, handing off between phase agents and pausing for user confirmation at each gate.

## Task

${input:task:Describe the task in 1–3 sentences (what to build / fix / change)}

## Optional Context

- Target service(s): ${input:services:e.g. backend, chat-service, frontend, or "auto-detect"}
- Constraints / deadlines: ${input:constraints:e.g. must be backward compatible, ship behind flag X, none}

---

## Orchestration Rules

1. **Run phases in order.** Do not skip ahead. Each phase has its own agent definition in `.github/agents/`.
2. **Pause for confirmation at each gate.** After each phase produces its artifact, summarize and ask the user to approve before moving on.
3. **Stay grounded.** Every phase must use the existing `smartbid-*` skills and `.github/copilot-instructions.md` — do not invent project conventions.
4. **One step at a time during Implementation.** Run the Implementer on one plan step, then the Reviewer on that same step, before moving to the next step.

---

## Phase 1 — Research

Invoke the `task-researcher` agent. Produce the **Research Brief** in the format defined in `.github/agents/task-researcher.agent.md`.

**Gate:** Present the brief. Ask:

> "Brief looks correct? Any of the Open Questions need answers before planning? Reply `approve` or specify changes."

Do not proceed until the user approves.

---

## Phase 2 — Plan

Invoke the `planner` agent with the approved brief. Produce the **Implementation Plan**.

**Gate:** Present the plan. Ask:

> "Plan approved? Reply `approve` or request edits (different approach, resequence, change scope)."

Do not proceed until the user approves.

---

## Phase 3 — Implement (looped per step)

For each step in the plan, in order:

1. Invoke the `implementer` agent for that single step.
2. After it reports completion (tests green, criteria met), immediately invoke the `reviewer` agent on the same step.
3. Apply the reviewer's verdict:
    - **APPROVE / APPROVE WITH NITS** → record nits, proceed to the next step.
    - **REQUEST CHANGES** → hand back to `implementer` with the blocking findings.
    - **ESCALATE TO PLANNER** → stop the loop, return to Phase 2 with the reviewer's reasoning.

**Gate after each step:** Brief one-line status (step N done / failed / escalated). Ask before starting the next step only if the previous step had non-trivial deviations.

---

## Phase 4 — Sprint Close

When all steps are APPROVE (or APPROVE WITH NITS that the user accepted):

Produce a **Sprint Summary**:

```markdown
# Sprint Summary: <task title>

## Shipped

- Step 1 — <title> ✅
- Step 2 — <title> ✅
- …

## Test Results

- Backend: `pytest …` — N passed
- Frontend: `npx vitest run …` — N passed

## Deferred Nits

- file:line — <nit>

## Follow-ups (out of scope for this sprint)

- <items the Planner explicitly excluded>

## Suggested Commit / PR

- Branch: `feature/<JIRA-ID>-<short-desc>`
- Title: <one-liner>
- Body: <bullet list of step titles>
```

Ask whether to draft the PR (do not push without explicit confirmation, per repo safety rules).

---

## Hard Constraints

- DO NOT skip the Research phase — even for "obvious" changes, produce at least a minimal brief.
- DO NOT collapse Implement+Review into a single phase. Reviewer must see the actual diff.
- DO NOT push, force-push, or merge anything without explicit user confirmation.
- DO NOT change project conventions defined in `.github/copilot-instructions.md` or the `smartbid-*` skills — flag conflicts to the user instead.
