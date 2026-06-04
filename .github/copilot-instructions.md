# Project Guidelines — Arup Smart Bid

## Core Principles

- Follow **Microsoft recommended practices** and official documentation. When in doubt, consult [Microsoft Learn](https://learn.microsoft.com/) via the MS Docs MCP tools.
- Be direct and accurate. Do not pad responses with unnecessary praise, caveats, or filler.
- Prefer **Microsoft Agent Framework** (`agent-framework`, `agent-framework-azure-ai`) for all new AI orchestration work. Do not introduce LangChain, LlamaIndex, CrewAI, or other third-party orchestration frameworks.
- Legacy Semantic Kernel code exists in `backend/` v1 endpoints — do not extend it. New work should use Agent Framework.

## Tech Stack

| Layer | Stack |
|-------|-------|
| Backend (refactored) | Python 3.12, Azure Functions v4, Microsoft Agent Framework |
| Backend (legacy v1) | Python 3.12, Azure Functions v4, Semantic Kernel (do not extend) |
| Chat Service | Python 3.12, Azure Functions v4, Microsoft Agent Framework |
| Frontend | React 19, TypeScript, Vite, MUI 7, Vitest |
| Auth | Azure AD / MSAL |
| Storage | Azure Blob Storage, Azure Cosmos DB |
| Search | Azure AI Search |
| AI | Azure OpenAI, Azure Document Intelligence |
| Observability | OpenTelemetry, Azure Monitor |

## Architecture

This is a monorepo with 3 main service areas:

- `backend/` — Refactored backend (Agent Framework + legacy SK endpoints)
- `chat-service/` — Conversational AI service using Agent Framework
- `frontend/` — React SPA

See `docs/` for architecture diagrams, chat design, and RAG implementation notes.

## Python Conventions

- Use `pydantic` v2 for data models and validation.
- Use `azure-identity` and `DefaultAzureCredential` for authentication — prefer Managed Identity over API keys.
- Pin dependency versions in `requirements.txt` for deployable services.
- Use `async`/`await` for I/O-bound operations.
- Follow the existing project structure: `api/`, `core/`, `plugins/`, `planners/`, `workflows/`, `shared/`.
- Use OpenTelemetry for observability — do not introduce `print()` or `logging.debug()` for production tracing.

## Frontend Conventions

- TypeScript strict mode. No `any` types without justification.
- Use MUI components and theming — do not add alternative UI libraries.
- Tests use Vitest and React Testing Library.
- Lint with ESLint before committing.

## Azure Functions

- HTTP triggers with appropriate `AuthLevel` (`ANONYMOUS` for health, `FUNCTION` for protected endpoints).
- Keep function handlers thin — delegate to planners, workflows, or services.
- Configure settings via environment variables (`local.settings.json` locally, App Settings / Key Vault in Azure).
- Never commit secrets.

## Git & Branching

Follow the branching strategy in [BEST_PRACTICES.md](../BEST_PRACTICES.md):
- `main` → production, `dev` → integration
- Branch naming: `feature/<JIRA-ID>-<description>`, `bugfix/...`, `hotfix/...`
- All changes via pull requests with review

## Testing

- Backend: `pytest` + `pytest-asyncio`
- Frontend: `vitest` + React Testing Library
- All core logic must have tests. Tests must pass before merge.

## What Not To Do

- Do not use LangChain, LlamaIndex, or non-Microsoft AI orchestration frameworks.
- Do not add Semantic Kernel code to new features — use Agent Framework instead.
- Do not bypass branch protection or push directly to `main`/`dev`.
- Do not hardcode secrets, connection strings, or keys.
- Do not introduce new UI component libraries alongside MUI.
