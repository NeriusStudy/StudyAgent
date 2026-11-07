$ErrorActionPreference = "Stop"

# 定义检查失败时中止脚本的函数
function Invoke-CheckedCommand {
    param([scriptblock]$Command, [string]$ErrorMessage)
    & $Command
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: $ErrorMessage (Exit code: $LASTEXITCODE)" -ForegroundColor Red
        exit $LASTEXITCODE
    }
}

Write-Host "==> uv sync --all-packages" -ForegroundColor Cyan
Invoke-CheckedCommand { uv sync --all-packages } "Dependency sync failed"

Write-Host "==> uv run lint-imports" -ForegroundColor Cyan
Invoke-CheckedCommand { uv run lint-imports } "Import linter failed"

Write-Host "==> Smoke test: all core packages importable" -ForegroundColor Cyan
Invoke-CheckedCommand { uv run --package agentserver python -c "import agentschema, agentcore, agentllm, agentserver; print('all core packages importable')" } "Core packages import test failed"

Write-Host "==> MCP package import check" -ForegroundColor Cyan
Invoke-CheckedCommand { uv run --package agentserver python -c "import agentmcp; from agentmcp import MCPClientManager, MCPToolAdapter; print('MCP package OK')" } "MCP package import test failed"

Write-Host "==> MCP adapter field compatibility check" -ForegroundColor Cyan
Invoke-CheckedCommand { uv run --package agentserver python -c "from agentmcp.adapter import MCPToolAdapter; print('MCPToolAdapter OK')" } "MCP adapter test failed"

Write-Host "==> ALL CHECKS PASSED" -ForegroundColor Green