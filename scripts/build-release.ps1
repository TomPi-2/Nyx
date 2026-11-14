<#
.SYNOPSIS
  Construye una versión de Nyx para publicar (tareas 9.07, 9.06 y 9.08).

.DESCRIPTION
  1. El núcleo empaquetado (core/scripts/package_core.py): Python 3.14 oficial, dependencias
     de uv.lock con sus huellas, el núcleo y whisper-server.
  2. La app (Tauri, sin instalador propio: lo pone Velopack).
  3. El paquete de Velopack (vpk, herramienta local: .config/dotnet-tools.json):
     TepnyxNyx-win-Setup.exe, el paquete completo y el feed para las actualizaciones.
  4. SHA256SUMS.txt (el instalador comprueba con él el Setup que descarga).
  5. El instalador de Nyx (installer/), con el Setup al lado para instalar sin internet.

  Todo queda en Releases\<versión>\. La firma (SignPath) y la subida a GitHub las hará la
  acción de publicación (9.09), cuando el repositorio sea público.

.PARAMETER Version
  SemVer (1.4.0, 0.9.0-beta.1). Por defecto, la de ui/src-tauri/tauri.conf.json.

.PARAMETER Whisper
  Carpeta con whisper-server.exe y sus DLL, compilado con Vulkan y sin GGML_NATIVE
  (docs/benchmarks/README.md). Por defecto, NYX_WHISPER_DIR.

.EXAMPLE
  .\scripts\build-release.ps1 -Version 0.9.0 -Whisper C:\dev\tools\whisper.cpp\build\bin\Release
#>
[CmdletBinding()]
param(
  [string]$Version,
  [string]$Whisper = $env:NYX_WHISPER_DIR
)

# En PowerShell 5.1, con «Stop» cualquier línea que un programa escriba en stderr (uv, npm,
# cargo…) cuenta como error: los programas se comprueban por su código de salida (Check) y los
# cmdlets llevan -ErrorAction Stop.
$ErrorActionPreference = "Continue"
$Repo = Split-Path -Parent $PSScriptRoot
$PackId = "TepnyxNyx"
$MainExe = "nyx-ui.exe"

function Step($text) { Write-Host "`n== $text" -ForegroundColor Cyan }
function Check($what) { if ($LASTEXITCODE -ne 0) { throw "$what ha fallado ($LASTEXITCODE)" } }

if (-not $Version) {
  $Version = (Get-Content "$Repo\ui\src-tauri\tauri.conf.json" -Raw | ConvertFrom-Json).version
}
if ($Version -notmatch '^\d+\.\d+\.\d+(-[0-9A-Za-z.-]+)?$') { throw "Versión no válida: $Version" }
if (-not $Whisper -or -not (Test-Path "$Whisper\whisper-server.exe")) {
  throw "Falta whisper-server: pasa -Whisper o pon NYX_WHISPER_DIR"
}

$Out = Join-Path $Repo "Releases\$Version"
# La versión para Tauri en un archivo: PowerShell 5.1 quita las comillas de un JSON en línea.
$VersionConfig = Join-Path $env:TEMP "nyx-version.json"
'{"version": "' + $Version + '"}' | Set-Content $VersionConfig -Encoding ascii
$Pack = Join-Path $Repo "dist\pack"
foreach ($dir in @($Out, $Pack)) {
  if (Test-Path $dir) {
    # Nunca borrado permanente: lo de una construcción anterior va a la papelera.
    Add-Type -AssemblyName Microsoft.VisualBasic
    [Microsoft.VisualBasic.FileIO.FileSystem]::DeleteDirectory(
      $dir, 'OnlyErrorDialogs', 'SendToRecycleBin')
  }
}
New-Item -ItemType Directory -Force $Out, $Pack -ErrorAction Stop | Out-Null

Step "Núcleo empaquetado"
Push-Location "$Repo\core"
uv run python scripts/package_core.py --out "$Pack\core" --whisper "$Whisper"; Check "package_core"
Pop-Location

Step "App (Tauri)"
Push-Location "$Repo\ui"
# Sin borrar node_modules (npm ci lo borra entero y falla si el editor tiene algo abierto).
if (-not (Test-Path node_modules)) { npm install; Check "npm install (ui)" }
# La versión del núcleo es la de la app: la que se publica.
npx tauri build --no-bundle --config $VersionConfig; Check "tauri build (ui)"
Copy-Item "src-tauri\target\release\$MainExe" $Pack -ErrorAction Stop
Pop-Location

Step "Paquete de Velopack ($Version)"
Push-Location $Repo
dotnet tool restore; Check "dotnet tool restore"
dotnet vpk pack --packId $PackId --packVersion $Version --packDir $Pack --mainExe $MainExe `
  --packTitle "Nyx" --packAuthors "Tepnyx" --icon "$Repo\ui\src-tauri\icons\icon.ico" `
  --outputDir $Out; Check "vpk pack"
Pop-Location

Step "Huellas"
$sums = Get-ChildItem $Out -File | ForEach-Object {
  "{0}  {1}" -f (Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLower(), $_.Name
}
$sums | Set-Content "$Out\SHA256SUMS.txt" -Encoding ascii

Step "Instalador"
Push-Location "$Repo\installer"
# Sin borrar node_modules (npm ci lo borra entero y falla si el editor tiene algo abierto).
if (-not (Test-Path node_modules)) { npm install; Check "npm install (installer)" }
npx tauri build --no-bundle --config $VersionConfig; Check "tauri build (installer)"
Copy-Item "src-tauri\target\release\nyx-installer.exe" "$Out\Instalar Nyx.exe" -ErrorAction Stop
Pop-Location

Step "Listo"
Get-ChildItem $Out | Select-Object Name, @{ n = "MB"; e = { [math]::Round($_.Length / 1MB, 1) } } |
  Format-Table -AutoSize
Write-Host "Para instalar sin internet: «Instalar Nyx.exe» junto a $PackId-win-Setup.exe."
