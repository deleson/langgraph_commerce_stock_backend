

# 阶段九回归测试检查清单

## 一、检查清单目的

阶段九用于确认当前后端项目已经具备可重复执行的自动化测试基础。

本阶段的目标不是证明所有量化公式都完全正确，也不是证明真实 LLM 回答质量一定优秀。

本阶段的目标是确认：

```text
核心 API 能稳定运行
认证和当前用户能力正常
用户隔离可靠
AI 主分析链路可以用 Mock LLM 验证
ReAct 多轮追问可以用 Mock LLM 验证
后台任务 API 可以测试
每日简报、量化提醒、纸面交易基础链路可以回归
测试库和开发库相互隔离
```

## 二、测试环境要求

运行测试前，需要确认当前终端使用测试环境：

```powershell
$env:APP_ENV_FILE='.env.test'
$env:UV_CACHE_DIR='.uv-cache'
```

测试数据库必须是：

```text
langgraph_commerce_test
```

测试环境应该使用：

```text
APP_ENV=test
LLM_PROVIDER=mock
MARKET_DATA_PROVIDER=mock
Celery Beat 关闭
```

## 三、完整回归测试命令

推荐命令：

```powershell
.\scripts\run_stage9_tests.ps1
```

等价的手动命令：

```powershell
$env:APP_ENV_FILE='.env.test'
$env:UV_CACHE_DIR='.uv-cache'
uv run pytest tests -q
uv run python -m compileall app tests
```

## 四、分组运行命令

| 分组 | 命令 | 覆盖范围 |
| --- | --- | --- |
| smoke | `.\scripts\run_stage9_tests.ps1 -Target smoke` | FastAPI app 导入烟雾测试 |
| fixtures | `.\scripts\run_stage9_tests.ps1 -Target fixtures` | 通用测试夹具自检 |
| auth | `.\scripts\run_stage9_tests.ps1 -Target auth` | 注册、登录、刷新 token、退出、当前用户 |
| context | `.\scripts\run_stage9_tests.ps1 -Target context` | 自选股、用户偏好、通知 |
| market | `.\scripts\run_stage9_tests.ps1 -Target market` | 行情、K 线、指标、数据质量、策略信号 |
| ai | `.\scripts\run_stage9_tests.ps1 -Target ai` | Mock LLM 下的个股 AI 主分析 |
| react | `.\scripts\run_stage9_tests.ps1 -Target react` | ReAct 工具、多轮追问、Trace |
| research | `.\scripts\run_stage9_tests.ps1 -Target research` | 策略信号、回测、候选评分 |
| tasks | `.\scripts\run_stage9_tests.ps1 -Target tasks` | 后台任务提交、查询、取消、失败 |
| active | `.\scripts\run_stage9_tests.ps1 -Target active` | 每日简报、量化提醒、纸面交易 |
| isolation | `.\scripts\run_stage9_tests.ps1 -Target isolation` | 用户隔离、跨用户访问 404 |
| api | `.\scripts\run_stage9_tests.ps1 -Target api` | 全部 API 测试 |
| all | `.\scripts\run_stage9_tests.ps1 -Target all` | 全部测试 |

## 五、当前测试文件清单

| 文件 | 覆盖范围 |
| --- | --- |
| `tests/test_smoke.py` | FastAPI app 导入烟雾测试 |
| `tests/test_fixtures.py` | 通用测试夹具自检 |
| `tests/api/test_auth_users_api.py` | 注册、登录、刷新 token、退出、当前用户 |
| `tests/api/test_user_context_api.py` | 自选股、用户偏好、通知 |
| `tests/api/test_market_data_api.py` | 行情 API、K 线同步、指标、数据质量 |
| `tests/api/test_stock_analysis_mock_llm_api.py` | Mock LLM 下的主分析图 |
| `tests/api/test_stock_analysis_react_api.py` | ReAct 追问、工具调用、Trace |
| `tests/api/test_research_strategy_api.py` | 策略信号、单股回测、组合回测、候选评分 |
| `tests/api/test_background_tasks_api.py` | 后台任务 API |
| `tests/api/test_active_services_paper_trading_api.py` | 每日简报、量化提醒、纸面交易 |
| `tests/api/test_user_isolation_api.py` | 统一用户隔离测试 |

## 六、阶段九已经覆盖什么

阶段九已经覆盖：

```text
认证
当前用户接口
自选股
用户偏好
通知
行情基础接口
Mock K 线同步
技术指标可用性
数据质量可用性
策略信号可用性
Mock LLM 下的主分析图
普通追问
ReAct 多轮追问
ReAct 工具调用
分析会话消息
ReAct Trace
单股回测基础链路
组合回测基础链路
候选股票评分基础链路
后台任务 API
每日简报稳定分支
量化提醒稳定分支
纸面交易稳定分支
用户隔离
```

## 七、阶段九没有证明什么

阶段九没有证明：

```text
真实 LLM 回答质量
真实行情源稳定性
MA / RSI / MACD 等量化公式的严格数学正确性
回测资金曲线的严格一致性
纸面交易现金和持仓的严格一致性
生产部署可用性
Celery Worker 在所有测试中的真实端到端执行
Celery Beat 定时调度在所有测试中的真实执行
```

这些内容放到后续阶段：

```text
阶段九-A：量化专项测试
阶段十：部署与生产准备
阶段十点五：最终验收与交付评估
```

## 八、常见失败与处理方式

| 失败现象 | 常见原因 | 处理方式 |
| --- | --- | --- |
| 测试环境断言失败 | 没有使用 `.env.test` | 执行 `$env:APP_ENV_FILE='.env.test'` |
| 数据库表不存在 | 测试库没有执行迁移 | 设置 `.env.test` 后执行 `uv run alembic upgrade head` |
| `event loop is closed` | pytest async loop 配置被改动 | 检查 `pyproject.toml` 中 session loop 配置 |
| 调用了真实 LLM | Mock fixture 未生效或 `.env.test` 未加载 | 检查测试 fixture 和环境变量 |
| Mock 行情股票 404 | mock provider 不支持该 symbol | 使用 `AAPL`、`TSLA` |
| Decimal 断言不一致 | 数据库 Numeric 精度会保留小数位 | 按实际序列化值断言，例如 `100000.0000` |
| message 断言不一致 | 没有对齐 Service 真实错误消息 | 先看 Service 和已有测试再写断言 |
| Celery 连接失败 | 测试忘记 patch `send_task` | 使用 Mock Celery fixture |
| 列表出现其他用户数据 | Repository 可能没有按 `user_id` 过滤 | 检查对应 Repository 查询条件 |

## 九、提交前检查

提交阶段九测试相关改动前，建议先运行：

```powershell
.\scripts\run_stage9_tests.ps1 -Target api
```

然后运行：

```powershell
.\scripts\run_stage9_tests.ps1 -Target all
```

如果本地全量测试耗时较长，开发过程中至少运行本次改动相关测试文件，并执行：

```powershell
uv run python -m compileall app tests
```

## 十、安全规则

不要让测试清理逻辑连接开发数据库。

测试套件只有在以下条件满足时，才允许清理测试数据：

```text
APP_ENV=test
database_url 包含 langgraph_commerce_test
database_async_url 包含 langgraph_commerce_test
```
```

你把步骤十四中原来那段英文检查清单替换成这一版中文即可，其他部分不用动。