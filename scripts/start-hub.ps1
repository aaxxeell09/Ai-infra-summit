param(
    [string]$Model = 'qualcomm/Qwen3-VL-4B-Instruct',
    [string]$GenieXUrl = 'http://127.0.0.1:18181/v1',
    [int]$Port = 8080
)
$ErrorActionPreference = 'Stop'
$python = Join-Path $env:LOCALAPPDATA 'QualcommTools\Python314\python.exe'
if (-not (Test-Path $python)) {
    $python = (Get-Command python -ErrorAction Stop).Source
}
Set-Location (Split-Path $PSScriptRoot -Parent)
& $python -m inspection --model $Model --geniex-url $GenieXUrl --port $Port
exit $LASTEXITCODE
