# Hypervelocity Engineering (HVE) Workflow

A Copilot-native, role-specific agent workflow for Arup Smart Bid — modeled after the HVE Core pattern (Researcher → Planner → Implementer → Reviewer). Designed to let small teams ship production-ready outcomes in **1-week sprints** without losing quality.

> "HVE Core enabled hypervelocity by providing role-specific AI agents that accelerated planning, coding, and review, allowing teams to deliver production-ready outcomes in weekly cycles."

---

## What you get

Four specialised agents, one orchestration prompt, all grounded in the existing `.github/copilot-instructions.md` and the repo's `smartbid-*` skills.

| Phase        | Agent file                                                  | Role                                                                 | Edits code? | Tools                                                  |
| ------------ | ----------------------------------------------------------- | -------------------------------------------------------------------- | ----------- | ------------------------------------------------------ |
| 1. Research  | [task-researcher.agent.md](agents/task-researcher.agent.md) | Turn fuzzy ask → verified Research Brief                             | ❌          | read, search, web, agent, todo                         |
| 2. Plan      | [planner.agent.md](agents/planner.agent.md)                 | Brief → ordered Implementation Plan with tests & acceptance criteria | ❌          | read, search, todo                                     |
| 3. Implement | [implementer.agent.md](agents/implementer.agent.md)         | Execute one plan step with tests                                     | ✅          | read, edit, search, runCommands, runTasks, todo, agent |
| 4. Review    | [reviewer.agent.md](agents/reviewer.agent.md)               | Audit diff against `code-reviewer` skill, give verdict               | ❌          | read, search, web, todo                                |

Plus:

- [hve-sprint.prompt.md](prompts/hve-sprint.prompt.md) — one-shot orchestrator that drives all four phases on a single task with confirmation gates.

---

## How to use it

### Option A — Full sprint loop (recommended)

In Copilot Chat:

```
/hve-sprint
```

You'll be prompted for the task, target services, and constraints. The prompt drives Research → Plan → Implement → Review with a confirmation gate after each phase.

### Option B — Invoke a single phase

When you only need one role (e.g. "just help me plan this"):

```
@task-researcher  investigate how citations flow from chat-service to the UI
@planner          using the brief above, plan the migration to streaming responses
@implementer      execute Step 2 of the approved plan
@reviewer         audit the diff against the code-reviewer skill
```

### Option C — Mix with existing agents and skills

The HVE agents are designed to **compose with what's already in this repo**:

- `@codebase-mentor` for deep onboarding before research.
- `@Explore` subagent for read-only fan-out searches inside any phase.
- `smartbid-backend-endpoint`, `smartbid-chat-feature`, `smartbid-rag-pipeline`, `smartbid-local-setup`, `smartbid-troubleshoot` — loaded by the Planner/Implementer when their domain matches.
- `code-reviewer` skill — loaded by the Reviewer agent on every review.

---

## Why role-specific agents (vs. one generic assistant)

| Generic assistant                                                  | HVE role-specific agents                                             |
| ------------------------------------------------------------------ | -------------------------------------------------------------------- |
| One tool surface, easy to wander into code edits while researching | Read-only research/planning agents physically cannot edit            |
| Plans and code blur into the same response                         | Plan is a reviewable artifact before any code is written             |
| Review happens as an afterthought (or not at all)                  | Reviewer is a mandatory phase with its own checklist and verdict     |
| Quality drops as speed rises                                       | Each phase has explicit "Done when" criteria and handoff format      |
| Hard to delegate per-phase to humans                               | Any phase can be done by a human and the next agent picks up cleanly |

---

## The handoff contract (why this works in 1-week sprints)

Each phase produces a **structured artifact** the next phase can consume without re-discovering context:

```
User request
   │
   ▼
[Task Researcher] ──► Research Brief  ──┐
                                        │ (human gate)
                                        ▼
                              [Planner] ──► Implementation Plan ──┐
                                                                   │ (human gate)
                                                                   ▼
                                                       [Implementer] ──► Step Completion Report
                                                                                │
                                                                                ▼
                                                                          [Reviewer] ──► Verdict
                                                                                │
                                                              ┌─────────────────┴─────────────────┐
                                                              ▼                                   ▼
                                                       APPROVE → next step              REQUEST CHANGES → back to Implementer
                                                                                                ESCALATE → back to Planner
```

Because each artifact has a fixed format, you can stop and resume mid-sprint, hand a phase to a teammate, or split a long task across multiple chat sessions without losing state.

---

## Guardrails baked in

All HVE agents inherit the repo's existing safety posture:

- Microsoft Agent Framework only for new AI orchestration (no LangChain/LlamaIndex/CrewAI; no extending Semantic Kernel v1).
- Managed Identity / `DefaultAzureCredential` over API keys; never hardcode secrets.
- pydantic v2, OpenTelemetry, thin Function handlers.
- TypeScript strict, MUI-only, ESLint-clean on the frontend.
- No `--no-verify`, no `git reset --hard` on shared history, no force-push without confirmation.
- Reviewer must ground findings in official Microsoft Learn docs (via `code-reviewer` skill).

---

## Tuning for your team

- **Trivial changes** (one-line fix, typo): skip directly to `@implementer`. The agents will tell you when a phase is overkill.
- **Spike / research-only work**: stop after `@task-researcher` and use the brief as the deliverable.
- **Design-heavy work**: loop Research ↔ Plan a few times before any code.
- **Cross-team review**: hand the Reviewer's verdict markdown straight into the PR description.
