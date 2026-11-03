$ErrorActionPreference = "Stop"

Write-Host "==> uv sync --all-packages" -ForegroundColor Cyan
uv sync --all-packages

Write-Host "==> uv run lint-imports" -ForegroundColor Cyan
uv run lint-imports

Write-Host "==> smoke test: all four packages importable" -ForegroundColor Cyan
uv run --package agentserver python -c "import agentschema, agentcore, agentllm, agentserver; print('all four packages importable')"

Write-Host "==> ALL CHECKS PASSED" -ForegroundColor Green