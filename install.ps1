param(
  [string]$TargetRoot,
  [ValidateSet("codex")]
  [string]$Preset,
  [string[]]$Skill,
  [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Get-Command python -ErrorAction SilentlyContinue
if (-not $Python) {
  $Python = Get-Command py -ErrorAction SilentlyContinue
}
if (-not $Python) {
  throw "Python was not found on PATH. Run install.py with the target agent's Python interpreter."
}

$argsList = @((Join-Path $ScriptDir "install.py"))
if ($TargetRoot) {
  $argsList += @("--target-root", $TargetRoot)
}
if ($Preset) {
  $argsList += @("--preset", $Preset)
}
foreach ($item in $Skill) {
  $argsList += @("--skill", $item)
}
if ($DryRun) {
  $argsList += "--dry-run"
}

& $Python.Source @argsList
