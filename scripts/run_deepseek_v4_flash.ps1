$ErrorActionPreference = "Stop"

$project = Split-Path -Parent $PSScriptRoot
$python = Join-Path $project ".venv\Scripts\python.exe"
$runtimeConfig = Join-Path $PSScriptRoot "runtime_config"
$runName = "deepseek_v4_flash_smoke"

if (-not (Test-Path $python)) {
    throw "Project virtual environment not found. Create it with: py -3.12 -m venv .venv"
}
if ([string]::IsNullOrWhiteSpace($env:DEEPSEEK_API_KEY)) {
    throw "DEEPSEEK_API_KEY is not available. Open a new PowerShell window after configuring it."
}

$versionOk = & $python -c "import sys; print(int(sys.version_info >= (3, 10)))"
if ($versionOk -ne "1") {
    throw "Python 3.10 or newer is required. Python 3.12 is recommended."
}

$env:PYTHONPATH = $project
$env:PYTHONDONTWRITEBYTECODE = "1"
Set-Location $runtimeConfig

$model = & $python -c "from evisi_eval.config import get_provider_config; print(get_provider_config('deepseek').model)"
if ($model -ne "deepseek-v4-flash") {
    throw "Wrong model loaded: $model"
}

& $python -m evisi_eval check-provider --provider deepseek
if ($LASTEXITCODE -ne 0) { throw "DeepSeek connection failed." }

& $python -m evisi_eval run `
    --samples "$project\data\user_samples_v05\smoke\source_00_input.jsonl" `
    --outputs "$project\data\user_samples_v05\smoke\target_00_input.jsonl" `
    --provider deepseek `
    --output-dir "$project\results" `
    --run-name $runName
if ($LASTEXITCODE -ne 0) { throw "EviSI-Eval failed." }

Write-Host "Report: $project\results\$runName\report.html"
