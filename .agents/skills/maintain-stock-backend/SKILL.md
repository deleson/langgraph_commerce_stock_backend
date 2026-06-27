---
name: maintain-stock-backend
description: Maintain and extend the LangGraph Commerce FastAPI backend. Use for backend API, schema, service, repository, model, Alembic migration, market provider, quant, backtest, LangGraph, Celery, authentication, testing, Docker, deployment, debugging, or backend documentation tasks in this repository.
---

# Maintain Stock Backend

## Establish Context

1. Treat the repository containing this skill as the backend root.
2. Read the nearest applicable `AGENTS.md` before acting.
3. Read only the smallest relevant formal documents under `docs/`.
4. Inspect current code before explaining behavior or making changes. Treat code, migrations, configuration, and runtime evidence as authoritative when documentation differs.
5. Read [references/project-map.md](references/project-map.md) when the task crosses modules or the correct ownership boundary is unclear.

## Follow The Architecture

- Keep HTTP parsing, dependencies, authentication, and response construction in `app/api/routers/`.
- Keep request and response validation in `app/schemas/`.
- Put business rules and orchestration in `app/services/`.
- Put database reads, writes, and query composition in `app/repositories/`.
- Keep table definitions in `app/models/` and schema evolution in `alembic/versions/`.
- Keep external market calls and provider-specific normalization behind provider implementations.
- Keep LangGraph state, nodes, routing, and graph construction in `app/graphs/`.
- Keep Celery task functions as scheduling and execution entrypoints; call services for business work.
- Reuse existing response, exception, logging, security, database, Redis, and LLM helpers before adding abstractions.

## Execute Backend Work

1. Trace the affected flow from Router to Schema to Service, then Repository, Model, migration, task, or Graph as applicable.
2. Identify compatibility effects on Android clients, persisted data, background workers, and production configuration.
3. Make the smallest coherent change across all affected layers; do not patch only the first visible failure.
4. Add concise Chinese comments only where they explain a business invariant, provider choice, concurrency concern, or non-obvious design reason.
5. Update an existing `docs/` document when public behavior, architecture, configuration, or an API contract changes.
6. Add focused tests for the success path, invalid input, dependency failure, existing data, missing data, and idempotency when relevant.

## Preserve Domain Invariants

- Prefer persisted market data on user request paths. Use external providers for background synchronization or explicit missing-data fallback.
- Treat Tushare as the higher-priority source where configured; normalize BaoStock as a fallback without blindly overwriting higher-priority canonical data.
- Synchronize the stock symbol pool at low frequency. Synchronize K-line data only for watchlists, recently analyzed symbols, or explicitly requested symbols, never the full market.
- Keep AI analysis, strategy signals, backtests, candidate scoring, reports, alerts, and paper trading framed as research features, not investment advice.
- Never connect paper trading to a real broker or place real orders.
- Never expose or commit production secrets, tokens, passwords, private keys, or real server addresses.
- Do not run destructive database or Docker-volume commands unless the user explicitly requests them.

## Verify And Deliver

- Run focused tests first, then broader existing regression scripts when the blast radius warrants it.
- Set `APP_ENV_FILE=.env.test` and `UV_CACHE_DIR=.uv-cache` where required by the local test setup.
- Run database-cleaning pytest groups serially; parallel runs can deadlock on shared PostgreSQL truncation fixtures.
- At minimum, run relevant pytest tests, `python -m compileall` for changed Python areas, and `git diff --check` when feasible.
- For deployment changes, validate the production Compose configuration without printing secret values.
- Inspect `git status` and `git diff` before committing. Preserve unrelated user changes.
- Use an English Conventional Commit message. Push only when requested, and report the commit and remote result accurately.
