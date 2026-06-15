param(
    [ValidateSet("smoke", "fixtures", "auth", "context", "market", "ai", "react", "research", "tasks", "active", "isolation", "api", "all")]
    [string]$Target = "all",

    [switch]$SkipCompile
)

# 阶段九通用回归脚本。
#
# 这个脚本只用于本地或 CI 的测试环境：
# 1. 强制 APP_ENV_FILE=.env.test；
# 2. 校验数据库地址包含 langgraph_commerce_test；
# 3. 按分组运行 pytest；
# 4. 可选执行 compileall。
#
# 注意：不要把这个脚本指向开发库或生产库运行。

$ErrorActionPreference = "Stop"

$env:APP_ENV_FILE = ".env.test"

if (-not $env:UV_CACHE_DIR) {
    $env:UV_CACHE_DIR = ".uv-cache"
}

Write-Host "Stage 9 regression test runner"
Write-Host "APP_ENV_FILE=$env:APP_ENV_FILE"
Write-Host "UV_CACHE_DIR=$env:UV_CACHE_DIR"
Write-Host "Target=$Target"

Write-Host ""
Write-Host "Checking test environment..."
uv run python -c "from app.core.config import get_settings; s=get_settings(); assert s.app_env == 'test'; assert 'langgraph_commerce_test' in s.database_url; assert 'langgraph_commerce_test' in s.database_async_url; print(s.app_env); print(s.database_url); print(s.database_async_url)"

if ($LASTEXITCODE -ne 0) {
    throw "Test environment check failed."
}

# 每个 Target 对应一组测试文件。
# 这样日常开发可以先跑小分组，阶段验收时再跑 api 或 all。
$pytestArgs = @()

if ($Target -eq "smoke") { $pytestArgs = @("tests/test_smoke.py", "-q") }
if ($Target -eq "fixtures") { $pytestArgs = @("tests/test_fixtures.py", "-q") }
if ($Target -eq "auth") { $pytestArgs = @("tests/api/test_auth_users_api.py", "-q") }
if ($Target -eq "context") { $pytestArgs = @("tests/api/test_user_context_api.py", "-q") }
if ($Target -eq "market") { $pytestArgs = @("tests/api/test_market_data_api.py", "-q") }
if ($Target -eq "ai") { $pytestArgs = @("tests/api/test_stock_analysis_mock_llm_api.py", "-q") }
if ($Target -eq "react") { $pytestArgs = @("tests/api/test_stock_analysis_react_api.py", "-q") }
if ($Target -eq "research") { $pytestArgs = @("tests/api/test_research_strategy_api.py", "-q") }
if ($Target -eq "tasks") { $pytestArgs = @("tests/api/test_background_tasks_api.py", "-q") }
if ($Target -eq "active") { $pytestArgs = @("tests/api/test_active_services_paper_trading_api.py", "-q") }
if ($Target -eq "isolation") { $pytestArgs = @("tests/api/test_user_isolation_api.py", "-q") }
if ($Target -eq "api") { $pytestArgs = @("tests/api", "-q") }
if ($Target -eq "all") { $pytestArgs = @("tests", "-q") }

if (-not $pytestArgs) {
    throw "Unknown test target: $Target"
}

Write-Host ""
Write-Host "Running pytest..."
Write-Host "pytest args: $($pytestArgs -join ' ')"
uv run pytest @pytestArgs

if ($LASTEXITCODE -ne 0) {
    throw "pytest failed."
}

if (-not $SkipCompile) {
    Write-Host ""
    Write-Host "Running compileall..."
    uv run python -m compileall app tests

    if ($LASTEXITCODE -ne 0) {
        throw "compileall failed."
    }
}

Write-Host ""
Write-Host "Stage 9 regression finished successfully."
