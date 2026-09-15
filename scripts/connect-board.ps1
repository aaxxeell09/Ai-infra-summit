param([string]$Serial = '')
$ErrorActionPreference = 'Stop'
$adb = Join-Path $env:LOCALAPPDATA 'QualcommTools\platform-tools\adb.exe'
if (-not (Test-Path $adb)) { $adb = (Get-Command adb -ErrorAction Stop).Source }
if (-not $Serial) {
    $devices = @(& $adb devices | Where-Object { $_ -match '\tdevice$' } | ForEach-Object { ($_ -split '\s+')[0] })
    if ($devices.Count -ne 1) { throw 'Connect one authorized UNO Q, or specify -Serial.' }
    $Serial = $devices[0]
}
$boardDir = '/home/arduino/ArduinoApps/inspection-station/data'
& $adb -s $Serial shell mkdir -p $boardDir
if ($LASTEXITCODE -ne 0) { throw 'Could not create the board socket directory.' }
# A filesystem socket is shared into App Lab without exposing a board TCP port.
& $adb -s $Serial reverse "localfilesystem:$boardDir/hub.sock" tcp:8080
if ($LASTEXITCODE -ne 0) { throw 'USB forwarding failed.' }
& $adb -s $Serial shell chmod 600 "$boardDir/hub.sock"
if ($LASTEXITCODE -ne 0) { throw 'Could not restrict the board socket permissions.' }
Write-Host 'UNO Q connected to the local inspection hub over USB.'
