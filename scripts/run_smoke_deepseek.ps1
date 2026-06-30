param(
    [string]$RunName = "smoke_v05",
    [string]$ReviewProvider = ""
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$arguments = @(
    "-m", "evisi_eval", "run",
    "--samples", "data\user_samples_v05\smoke\source_00_input.jsonl",
    "--outputs", "data\user_samples_v05\smoke\target_00_input.jsonl",
    "--provider", "deepseek",
    "--output-dir", "results",
    "--run-name", $RunName
)
if ($ReviewProvider) {
    $arguments += @("--review-provider", $ReviewProvider)
}

python @arguments
if ($LASTEXITCODE -ne 0) {
    throw "EviSI-Eval failed with exit code $LASTEXITCODE"
}

Write-Host "Result: $repoRoot\results\$RunName\report.html"
