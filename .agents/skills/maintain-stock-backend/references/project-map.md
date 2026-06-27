# Backend Project Map

## Read By Task

| Task | Start here | Continue with |
|---|---|---|
| API behavior | `app/api/routers/` | `app/schemas/`, relevant service |
| Database behavior | relevant service | `app/repositories/`, `app/models/`, `alembic/versions/` |
| Authentication and sessions | `app/api/routers/auth.py` | dependencies, security, auth/session services and models |
| Stock search and market data | market routers | market symbol, candle, provider, sync services and repositories |
| Technical indicators and signals | indicator/signal routers | technical indicator and strategy signal services |
| Backtests | backtest routers | single-stock and portfolio backtest services and schemas |
| AI analysis | stock analysis router | analysis services, graph definitions, nodes, states, LLM configuration |
| ReAct follow-up | conversation router | ReAct service, graph, routers, nodes, trace persistence |
| Reports, alerts, paper trading | corresponding routers | services, repositories, models, background tasks |
| Scheduled work | `app/core/celery_app.py` | `app/tasks/background_tasks.py`, background-task service |
| Production deployment | `docs/部署与环境说明.md` | Compose, Dockerfile, Nginx, example environment files |

## Layer Flow

```text
HTTP -> Router -> Schema -> Service -> Repository -> PostgreSQL
                            |-> Redis/cache
                            |-> Provider normalization -> Tushare/BaoStock
                            |-> LangGraph -> DeepSeek
Celery Beat -> Task entry -> Service -> Repository/Provider
```

## Formal Documentation

Read only what the task needs:

1. `docs/项目介绍.md`
2. `docs/前端对接指南.md`
3. `docs/业务术语与数据字典.md`
4. `docs/api全面介绍.md`
5. `docs/图结构介绍.md`
6. `docs/量化策略介绍.md`
7. `docs/回测业务介绍.md`
8. `docs/部署与环境说明.md`

Historical stage documents outside this repository explain decisions, but they do not override current code.
