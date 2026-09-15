$ErrorActionPreference = 'Stop'
$geniex = Join-Path $env:LOCALAPPDATA 'QualcommTools\GenieX\geniex.exe'
if (-not (Test-Path $geniex)) {
    $geniex = (Get-Command geniex -ErrorAction Stop).Source
}
& $geniex --skip-update --log info serve --compute npu --host '127.0.0.1:18181' --keepalive 3600
exit $LASTEXITCODE
