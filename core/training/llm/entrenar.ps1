# Lanza el entrenamiento del LoRA (6.27) en un proceso aparte, que sigue aunque se cierre la
# terminal o la sesión de Claude. Si ya hay guardados en output/checkpoints, retoma desde ahí.
#
#   powershell -ExecutionPolicy Bypass -File core/training/llm/entrenar.ps1
#
# Antes: cerrar Nyx. Este script saca el modelo de Ollama de la gráfica (no caben los dos).

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $here
# Todos los modelos cargados, no solo qwen2.5:7b (la batería deja los que mide, p. ej. nyx-r2:7b).
try {
    $loaded = (Invoke-RestMethod -Uri http://127.0.0.1:11434/api/ps).models
    foreach ($m in $loaded) {
        $body = @{ model = $m.name; keep_alive = 0 } | ConvertTo-Json
        Invoke-RestMethod -Method Post -Uri http://127.0.0.1:11434/api/generate `
            -Body $body -ContentType 'application/json' | Out-Null
    }
} catch { }
$env:PYTHONIOENCODING = "utf-8"
$env:HIP_VISIBLE_DEVICES = "0"
$env:HF_HUB_DISABLE_XET = "1"
New-Item -ItemType Directory -Force output | Out-Null
Start-Process -FilePath "$here\.venv\Scripts\python.exe" -ArgumentList "train.py" `
    -WorkingDirectory $here -WindowStyle Hidden `
    -RedirectStandardOutput "$here\output\train.log" -RedirectStandardError "$here\output\train.err"
Write-Output "Entrenamiento lanzado: output\train.log"
