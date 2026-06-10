param(
    [ValidateSet("smoke", "fixtures", "auth", "context", "market", "ai", "react", "research", "tasks", "active", "isolation", "api", "all")]
    [string]$Target = "all",

    [switch]$SkipCompile
)

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

$pytestArgs = @()

switch ($Target) {
    "smoke" {
        $pytestArgs = @("tests/test_smoke.py", "-q")
    }
    "fixtures" {
        $pytestArgs = @("tests/test_fixtures.py", "-q")
    }
    "auth" {
        $pytestArgs = @("tests/api/test_auth_users_api.py", "-q")
    }
    "context" {
        $pytestArgs = @("tests/api/test_user_context_api.py", "-q")
    }
    "market" {
        $pytestArgs = @("tests/api/test_market_data_api.py", "-q")
    }
    "ai" {
        $pytestArgs = @("tests/api/test_stock_analysis_mock_llm_api.py", "-q")
    }
    "react" {
        $pytestArgs = @("tests/api/test_stock_analysis_react_api.py", "-q")
    }
    "research" {
        $pytestArgs = @("tests/api/test_research_strategy_api.py", "-q")
    }
    "tasks" {
        $pytestArgs = @("tests/api/test_background_tasks_api.py", "-q")
    }
    "active" {
        $pytestArgs = @("tests/api/test_active_services_paper_trading_api.py", "-q")
    }
    "isolation" {
        $pytestArgs = @("tests/api/test_user_isolation_api.py", "-q")
    }
    "api" {
        $pytestArgs = @("tests/api", "-q")
    }
    "all" {
        $pytestArgs = @("tests", "-q")
    }
}

Write-Host ""
Write-Host "Running pytest..."
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