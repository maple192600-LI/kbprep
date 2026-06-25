param(
    [switch]$Full,
    [switch]$List
)

$ErrorActionPreference = "Stop"
$projectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")

$command = if ($Full) { "npm run dev:full-check" } else { "npm run dev:check" }

if ($List) {
    "[KBPrep verification] {0} :: {1}" -f $projectRoot.Path, $command
    exit 0
}

Push-Location $projectRoot.Path
try {
    powershell -NoProfile -Command $command
}
finally {
    Pop-Location
}
