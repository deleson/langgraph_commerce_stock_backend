# AGENTS.md

本文件是 `backend/` 后端项目的 AI Agent、Codex 和自动化开发工具入口。项目级跨模块规则仍以仓库根目录 `AGENTS.md` 为准；本文件只补充后端内部阅读顺序、分层边界和验证要求。

## 一、后端当前状态

后端主线已经完成用户、行情、AI 分析、量化、回测、日报、提醒、纸面交易、后台任务、测试和生产部署等核心能力。

当前阶段不是重新搭建后端，而是：

```text
1. 配合 Android 对接修正真实业务问题；
2. 完善稳定性、测试、日志和可维护性；
3. 补齐 HTTPS、备份、监控、限流等生产能力；
4. 保持正式文档与当前代码同步。
```

## 二、必读文档

| 任务 | 必读文档 |
| --- | --- |
| 整体理解 | `docs/项目介绍.md` |
| Android 或未来 Web 对接 | `docs/前端对接指南.md`、`docs/api全面介绍.md`、`docs/业务术语与数据字典.md` |
| AI 分析与追问 | `docs/图结构介绍.md` |
| 指标、信号、候选评分 | `docs/量化策略介绍.md` |
| 单股或组合回测 | `docs/回测业务介绍.md` |
| Docker、环境或生产排查 | `docs/部署与环境说明.md` |

历史阶段决策位于仓库根目录：

```text
../docs/backend/后端开发文档.md
../docs/backend/项目流程计划/
```

历史文档只解释设计背景，实际行为以当前代码、迁移、配置和运行结果为准。

## 三、代码分层

```text
app/api/routers/   # HTTP 路由、鉴权依赖、请求和响应边界
app/schemas/       # Pydantic 请求、响应、枚举和校验
app/services/      # 业务编排、量化规则、AI、回测和纸面交易逻辑
app/repositories/  # 数据库访问、用户隔离、分页和持久化
app/models/        # SQLAlchemy 数据表
app/graphs/        # LangGraph 状态、节点、条件路由和 ReAct 工具循环
app/tasks/         # Celery 后台任务
app/core/          # 配置、数据库、Redis、JWT、LLM、异常、日志和中间件
alembic/versions/  # 数据库结构迁移历史
tests/             # API、Service、Repository、Task 和量化测试
```

依赖方向应保持为：

```text
Router -> Schema / Service -> Repository / Model
Service -> Graph / Provider / Redis / Celery
```

不得把复杂业务规则直接写进 Router，也不得让前端承担后端 Provider 选择、策略计算或用户数据隔离。

## 四、重点调用链

### API 行为

```text
app/api/routers/
app/schemas/
app/services/
```

### 数据库与迁移

```text
app/models/
app/repositories/
alembic/versions/
```

### AI 主分析与 ReAct 追问

```text
app/api/routers/stock_analysis.py
app/services/stock_analysis_service.py
app/services/stock_analysis_react_service.py
app/graphs/stock_analysis_graph.py
app/graphs/stock_analysis_react_graph.py
app/graphs/nodes.py
app/graphs/react_nodes.py
```

### 量化、回测与纸面交易

```text
app/services/technical_indicator_service.py
app/services/strategy_signal_service.py
app/services/backtest_service.py
app/services/portfolio_backtest_service.py
app/services/stock_candidate_scoring_service.py
app/services/paper_trading_*.py
```

## 五、修改与验证要求

后端开发任务默认执行：

```text
1. 阅读相关正式文档和代码；
2. 确认 Router、Schema、Service、Repository、Model、Migration、测试和文档影响；
3. 按现有异步分层、命名和用户隔离方式修改；
4. 补充与改动范围匹配的测试；
5. 执行最小相关测试，再按风险决定是否运行完整测试；
6. 检查迁移、Compose、Git diff 和敏感信息。
```

常用验证命令：

```powershell
$env:APP_ENV_FILE='.env.test'
$env:UV_CACHE_DIR='.uv-cache'
uv run python -m compileall app tests
uv run pytest tests -q
docker compose --env-file .env.production.example -f docker-compose.prod.yml config --quiet
```

如果 PostgreSQL、Redis、Docker 或外部 Provider 不可用，必须说明哪些验证未执行，不得声称完整测试或生产链路通过。

## 六、安全与业务边界

```text
AI 分析、技术指标、策略信号、候选评分、回测、日报、提醒和纸面交易不构成投资建议；
历史回测不代表未来表现；
纸面交易不连接券商、不真实下单；
.env.production、密钥、Token、密码和 SSH 私钥不得提交或输出；
PostgreSQL、Redis 和 FastAPI 内部端口不得直接暴露公网；
未经用户明确要求，不得执行 DROP、TRUNCATE、删除 Volume 或 docker compose down -v。
```
