param([int]$Hours = 12)
$ErrorActionPreference = 'Stop'
# Process-scoped request; Windows releases it when this process exits.
Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class TurboAwake {
    [DllImport("kernel32.dll", SetLastError=true)]
    public static extern uint SetThreadExecutionState(uint flags);
}
'@
$deadline = (Get-Date).AddHours($Hours)
try {
    while ((Get-Date) -lt $deadline) {
        $previous = [TurboAwake]::SetThreadExecutionState([uint32]2147483651)
        if ($previous -eq 0) { throw 'SetThreadExecutionState failed' }
        Start-Sleep -Seconds 30
    }
} finally {
    [void][TurboAwake]::SetThreadExecutionState([uint32]2147483648)
}
