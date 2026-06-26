Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Push-Location $PSScriptRoot\..
try {
  python -m evisi_eval build-card --input data/raw_samples.jsonl --output data/cards.jsonl
  python -m evisi_eval run-eval --cards data/cards.jsonl --outputs data/system_outputs.jsonl --output data/eval_results.jsonl
  python -m evisi_eval export-report --input data/eval_results.jsonl --output reports/demo_report.html
  python -m evisi_eval build-card --input data/labeled_raw_samples.jsonl --output data/labeled_cards.jsonl
  python -m evisi_eval run-eval --cards data/labeled_cards.jsonl --outputs data/labeled_system_outputs.jsonl --output data/labeled_eval_results.jsonl
  python -m evisi_eval export-report --input data/labeled_eval_results.jsonl --output reports/labeled_demo_report.html
  Write-Host "Demo complete: reports/demo_report.html"
  Write-Host "Labeled demo complete: reports/labeled_demo_report.html"
}
finally {
  Pop-Location
}
