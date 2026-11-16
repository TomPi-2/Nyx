<#
.SYNOPSIS
  Publica una versión de Nyx (o el cerebro) en las Releases de GitHub (tarea 9.09).

.DESCRIPTION
  Sube lo que ha dejado build-release.ps1 en Releases\<versión>\ a la Release v<versión> de
  github.com/TomPi-2/Nyx, donde lo buscan el instalador y las actualizaciones de Nyx
  (Velopack, ui/src-tauri/src/updater.rs). Con -Brain sube además los trozos del cerebro de
  dist\brain\ a la Release cerebro-r2 (core/nyx/setup/brain.py).

  - Necesita la CLI de GitHub con sesión iniciada (`winget install GitHub.cli`; `gh auth login`).
  - Mientras el repositorio sea privado, solo lo puede bajar quien tenga acceso: los usuarios
    de la beta lo verán cuando sea público.
  - La 0.9.0 se publica como versión normal (no «prerelease») aunque sea la beta: las
    prerelease solo las ve el canal beta de Nyx (Ajustes → General → Actualizaciones).
  - Sin firma (SignPath, con el repositorio público), Windows avisa al abrir el instalador.
  - -DryRun enseña lo que haría sin subir nada.

.EXAMPLE
  .\scripts\publish.ps1 -Version 0.9.0 -DryRun
  .\scripts\publish.ps1 -Version 0.9.0 -Brain
#>
param(
  [Parameter(Mandatory = $true)][string]$Version,
  [switch]$Prerelease,
  [switch]$Brain,
  [switch]$DryRun
)
$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent $PSScriptRoot
$Out = Join-Path $Repo "Releases\$Version"
$GhRepo = "TomPi-2/Nyx"

function Run([string[]]$Cmd) {
  Write-Host ("> gh " + ($Cmd -join " "))
  if (-not $DryRun) {
    & gh @Cmd
    if ($LASTEXITCODE -ne 0) { throw "gh ha fallado ($LASTEXITCODE)" }
  }
}

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
  throw "Falta la CLI de GitHub: winget install GitHub.cli y después gh auth login"
}
if ($Version -notmatch '^\d+\.\d+\.\d+(-[0-9A-Za-z.-]+)?$') { throw "Versión no válida: $Version" }
$Files = @(
  "TepnyxNyx-win-Setup.exe", "TepnyxNyx-$Version-full.nupkg", "TepnyxNyx-win-Portable.zip",
  "releases.win.json", "assets.win.json", "RELEASES", "SHA256SUMS.txt", "Instalar Nyx.exe"
) | ForEach-Object { Join-Path $Out $_ }
$Missing = $Files | Where-Object { -not (Test-Path $_) }
if ($Missing) { throw "Faltan archivos (¿build-release.ps1?): $($Missing -join ', ')" }

# Las novedades de la versión: la sección «Sin publicar» del CHANGELOG, tal cual.
$Changelog = Get-Content (Join-Path $Repo "CHANGELOG.md") -Raw -Encoding UTF8
$Notes = [regex]::Match($Changelog, "(?s)## \[Sin publicar\]\s*(.*?)\n## \[").Groups[1].Value
$NotesFile = Join-Path $env:TEMP "nyx-notas-$Version.md"
Set-Content -Path $NotesFile -Value "Nyx $Version`n`n$Notes" -Encoding UTF8

$Create = @("release", "create", "v$Version") + $Files + @(
  "--repo", $GhRepo, "--title", "Nyx $Version", "--notes-file", $NotesFile, "--target", "main"
)
if ($Prerelease) { $Create += "--prerelease" }
Run $Create

if ($Brain) {
  $Parts = Get-ChildItem (Join-Path $Repo "dist\brain") -Filter "nyx-r2-7b.gguf.*" | ForEach-Object FullName
  if (-not $Parts) { throw "No hay trozos del cerebro en dist\brain (core/scripts/export_brain.py)" }
  Run (@("release", "create", "cerebro-r2") + $Parts + @(
    "--repo", $GhRepo, "--title", "Cerebro de Nyx (r2)",
    "--notes", "El cerebro de Nyx (qwen2.5:7b ajustado por Tepnyx, Apache-2.0) en trozos. Lo baja y comprueba Nyx en el primer arranque.",
    "--target", "main"
  ))
}
Write-Host "Listo$(if ($DryRun) { ' (sin subir nada: -DryRun)' })"
