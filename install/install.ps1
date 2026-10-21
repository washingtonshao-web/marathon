[CmdletBinding()]
param([switch]$Uninstall)
$ErrorActionPreference = 'Stop'
$pythonCommand = $null
$pythonArgs = @()
foreach ($candidate in @('python3', 'python', 'py')) {
    $command = Get-Command $candidate -ErrorAction SilentlyContinue
    if (-not $command) { continue }
    $prefix = @()
    if ($candidate -eq 'py') { $prefix = @('-3') }
    # A stub that prints to stderr (the Microsoft Store python3 alias) throws under 'Stop': try the next candidate.
    $ok = $false
    try {
        & $command.Source @prefix -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>$null
        $ok = ($LASTEXITCODE -eq 0)
    } catch { $ok = $false }
    if ($ok) {
        $pythonCommand = $command.Source
        $pythonArgs = $prefix
        break
    }
}
if (-not $pythonCommand) {
    Write-Host 'Python 3.10 or newer is required. Install it from https://www.python.org/downloads/ and run this installer again.'
    exit 1
}
$script = Join-Path $PSScriptRoot 'install.py'
if ($Uninstall) { & $pythonCommand @pythonArgs $script --uninstall }
else { & $pythonCommand @pythonArgs $script }
exit $LASTEXITCODE
