param(
    [ValidateSet(
        "fixtures",
        "market-repo",
        "data-quality",
        "technical",
        "signal",
        "backtest-equity",
        "backtest-metrics",
        "backtest-risk",
        "portfolio",
        "candidates",
        "paper-order",
        "paper-equity",
        "paper",
        "all"
    )]
    [string]$Target = "all",

    [switch]$SkipCompile
)

$ErrorActionPreference = "Stop"

$env:APP_ENV_FILE = ".env.test"

if (-not $env:UV_CACHE_DIR) {
    $env:UV_CACHE_DIR = ".uv-cache"
}

Write-Host "Stage 9-A quant regression test runner"
Write-Host "APP_ENV_FILE=$env:APP_ENV_FILE"
Write-Host "UV_CACHE_DIR=$env:UV_CACHE_DIR"
Write-Host "Target=$Target"

Write-Host ""
Write-Host "Checking test environment..."
uv run python -c "from app.core.config import get_settings; s=get_settings(); assert s.app_env == 'test'; assert 'langgraph_commerce_test' in s.database_url; assert 'langgraph_commerce_test' in s.database_async_url; print(s.app_env); print(s.database_url); print(s.database_async_url)"

if ($LASTEXITCODE -ne 0) {
    throw "Test environment check failed. Please confirm APP_ENV_FILE=.env.test and database points to langgraph_commerce_test."
}

$pytestArgs = @()

switch ($Target) {
    "fixtures" {
        $pytestArgs = @("tests/test_quant_data_fixtures.py", "-q")
    }
    "market-repo" {
        $pytestArgs = @("tests/repositories/test_market_repository_quant.py", "-q")
    }
    "data-quality" {
        $pytestArgs = @("tests/services/test_market_data_quality_quant.py", "-q")
    }
    "technical" {
        $pytestArgs = @("tests/services/test_technical_indicator_quant.py", "-q")
    }
    "signal" {
        $pytestArgs = @("tests/services/test_strategy_signal_quant.py", "-q")
    }
    "backtest-equity" {
        $pytestArgs = @("tests/services/test_backtest_equity_curve_quant.py", "-q")
    }
    "backtest-metrics" {
        $pytestArgs = @("tests/services/test_backtest_performance_metrics_quant.py", "-q")
    }
    "backtest-risk" {
        $pytestArgs = @("tests/services/test_backtest_risk_control_quant.py", "-q")
    }
    "portfolio" {
        $pytestArgs = @("tests/services/test_portfolio_backtest_quant.py", "-q")
    }
    "candidates" {
        $pytestArgs = @("tests/services/test_stock_candidate_scoring_quant.py", "-q")
    }
    "paper-order" {
        $pytestArgs = @("tests/services/test_paper_trading_order_trade_quant.py", "-q")
    }
    "paper-equity" {
        $pytestArgs = @("tests/services/test_paper_trading_position_equity_quant.py", "-q")
    }
    "paper" {
        $pytestArgs = @(
            "tests/services/test_paper_trading_order_trade_quant.py",
            "tests/services/test_paper_trading_position_equity_quant.py",
            "-q"
        )
    }
    "all" {
        $pytestArgs = @(
            "tests/test_quant_data_fixtures.py",
            "tests/repositories/test_market_repository_quant.py",
            "tests/services/test_market_data_quality_quant.py",
            "tests/services/test_technical_indicator_quant.py",
            "tests/services/test_strategy_signal_quant.py",
            "tests/services/test_backtest_equity_curve_quant.py",
            "tests/services/test_backtest_performance_metrics_quant.py",
            "tests/services/test_backtest_risk_control_quant.py",
            "tests/services/test_portfolio_backtest_quant.py",
            "tests/services/test_stock_candidate_scoring_quant.py",
            "tests/services/test_paper_trading_order_trade_quant.py",
            "tests/services/test_paper_trading_position_equity_quant.py",
            "-q"
        )
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
Write-Host "Stage 9-A quant regression finished successfully."
