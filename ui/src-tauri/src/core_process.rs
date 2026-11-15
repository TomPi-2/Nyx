//! Lanza y vigila el núcleo Python (proceso hijo).
//!
//! Contrato (ver core/nyx/main.py): token en NYX_TOKEN, línea JSON `{"event":"ready","port":N}`
//! en stdout al estar listo, y el núcleo termina cuando muere este proceso (NYX_PARENT_PID).

use std::path::PathBuf;
use std::process::Stdio;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use serde::{Deserialize, Serialize};
use tauri::{AppHandle, Emitter, Manager, State};

use crate::errors;
use tokio::io::{AsyncBufReadExt, BufReader};
use tokio::process::Command;
use tokio::sync::Notify;

/// Tras 3 caídas seguidas se deja de reiniciar hasta que el usuario lo pida (SPEC sección 14).
const MAX_FAILURES: u32 = 3;
/// Si el núcleo aguanta más que esto, la caída no cuenta como «seguida».
const HEALTHY_AFTER: Duration = Duration::from_secs(30);

#[derive(Clone, Serialize)]
pub struct CoreEndpoint {
    pub port: u16,
    pub token: String,
}

#[derive(Default)]
pub struct CoreState {
    endpoint: Mutex<Option<CoreEndpoint>>,
    restart: Notify,
    /// Parar del todo (para actualizar, 9.06): no se vuelve a lanzar.
    stopping: AtomicBool,
    stopped: Notify,
}

#[derive(Deserialize)]
struct ReadyLine {
    event: String,
    port: u16,
}

pub fn start(app: &AppHandle) {
    let state = Arc::new(CoreState::default());
    app.manage(state.clone());
    tauri::async_runtime::spawn(supervise(app.clone(), state));
}

/// Pide reiniciar el núcleo (menú de la bandeja).
pub fn restart(app: &AppHandle) {
    app.state::<Arc<CoreState>>().restart.notify_one();
}

/// Para el núcleo y no lo vuelve a lanzar (antes de aplicar una actualización, 9.06). Espera a
/// que termine, como mucho 10 s.
pub async fn stop(app: &AppHandle) {
    let state = app.state::<Arc<CoreState>>().inner().clone();
    state.stopping.store(true, Ordering::SeqCst);
    let stopped = state.stopped.notified();
    state.restart.notify_one();
    let _ = tokio::time::timeout(Duration::from_secs(10), stopped).await;
}

/// Vuelve a lanzar el núcleo tras `stop` (la actualización no se ha podido aplicar).
pub fn resume(app: &AppHandle) {
    let state = app.state::<Arc<CoreState>>().inner().clone();
    if state.stopping.swap(false, Ordering::SeqCst) {
        tauri::async_runtime::spawn(supervise(app.clone(), state));
    }
}

/// Ajustes → «Reiniciar ahora» (y Ayuda → Reiniciar Nyx): lo mismo que la bandeja.
#[tauri::command]
pub fn core_restart(app: AppHandle) {
    restart(&app);
}

#[tauri::command]
pub fn core_endpoint(state: State<'_, Arc<CoreState>>) -> Option<CoreEndpoint> {
    state.endpoint.lock().ok()?.clone()
}

async fn supervise(app: AppHandle, state: Arc<CoreState>) {
    let mut failures = 0u32;
    loop {
        let started = Instant::now();
        // Si ni siquiera se lanza (falta o un antivirus lo bloquea), es otro código.
        let mut missing = false;
        match run_once(&app, &state).await {
            Ok(status) => eprintln!("[nyx] el núcleo terminó: {status}"),
            Err(err) => {
                missing = true;
                eprintln!(
                    "[nyx] {}: no se pudo lanzar el núcleo: {err}",
                    errors::CORE_MISSING
                );
            }
        }
        if let Ok(mut endpoint) = state.endpoint.lock() {
            *endpoint = None;
        }
        let _ = app.emit("core://down", ());
        if state.stopping.load(Ordering::SeqCst) {
            state.stopped.notify_waiters();
            return;
        }

        failures = if started.elapsed() > HEALTHY_AFTER {
            1
        } else {
            failures + 1
        };
        if failures >= MAX_FAILURES {
            eprintln!(
                "[nyx] el núcleo ha fallado {failures} veces seguidas; esperando reinicio manual"
            );
            let _ = app.emit("core://failed", ());
            // Antes no se enseñaba nada: Nyx simplemente no contestaba.
            let code = if missing {
                errors::CORE_MISSING
            } else {
                errors::CORE_CRASHED
            };
            errors::notify(
                &app,
                code,
                "Nyx no puede arrancar",
                "Prueba con la bandeja → Reiniciar.",
            );
            state.restart.notified().await;
            failures = 0;
        } else {
            tokio::time::sleep(Duration::from_secs(1 << failures)).await;
        }
    }
}

async fn run_once(app: &AppHandle, state: &CoreState) -> Result<String, String> {
    let token = format!(
        "{}{}",
        uuid::Uuid::new_v4().simple(),
        uuid::Uuid::new_v4().simple()
    );
    let mut cmd = core_command();
    cmd.env("NYX_TOKEN", &token)
        // La versión del núcleo es la de la app (la de Velopack): una sola fuente (9.06).
        .env("NYX_APP_VERSION", app.package_info().version.to_string())
        // El núcleo vigila este PID para salir si Nyx muere (no lee stdin: con PyTorch se
        // colgaba). stdin sigue abierto como respaldo.
        .env("NYX_PARENT_PID", std::process::id().to_string())
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .kill_on_drop(true);
    #[cfg(windows)]
    {
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        cmd.creation_flags(CREATE_NO_WINDOW);
    }

    let mut child = cmd.spawn().map_err(|e| e.to_string())?;
    // Se mantiene abierto: al morir este proceso se cierra y el núcleo sale solo.
    let _stdin = child.stdin.take();

    if let Some(stderr) = child.stderr.take() {
        tauri::async_runtime::spawn(async move {
            let mut lines = BufReader::new(stderr).lines();
            while let Ok(Some(line)) = lines.next_line().await {
                eprintln!("[core] {line}");
            }
        });
    }

    let stdout = child.stdout.take().ok_or("sin stdout")?;
    let app_out = app.clone();
    tauri::async_runtime::spawn(async move {
        let mut lines = BufReader::new(stdout).lines();
        while let Ok(Some(line)) = lines.next_line().await {
            match serde_json::from_str::<ReadyLine>(&line) {
                Ok(ready) if ready.event == "ready" => {
                    let state = app_out.state::<Arc<CoreState>>();
                    if let Ok(mut endpoint) = state.endpoint.lock() {
                        *endpoint = Some(CoreEndpoint {
                            port: ready.port,
                            token: token.clone(),
                        });
                    }
                    let _ = app_out.emit("core://ready", ());
                }
                _ => eprintln!("[core:stdout] {line}"),
            }
        }
    });

    tokio::select! {
        status = child.wait() => status.map(|s| s.to_string()).map_err(|e| e.to_string()),
        _ = state.restart.notified() => {
            kill_tree(&child);
            let _ = child.kill().await;
            Ok("reinicio solicitado".into())
        }
    }
}

/// Mata el núcleo con todos sus descendientes. En desarrollo `child` es `uv`, que lanza
/// `nyx.exe` → `python.exe` → `whisper-server.exe`: matar solo `uv` dejaba vivo el núcleo de
/// verdad y, tras «Reiniciar núcleo», había dos escuchando el micrófono a la vez. Empaquetado,
/// `python.exe` → `whisper-server.exe`.
fn kill_tree(child: &tokio::process::Child) {
    #[cfg(windows)]
    if let Some(pid) = child.id() {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        let _ = std::process::Command::new("taskkill")
            .args(["/PID", &pid.to_string(), "/T", "/F"])
            .creation_flags(CREATE_NO_WINDOW)
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status();
    }
    #[cfg(not(windows))]
    let _ = child;
}

/// Orden para lanzar el núcleo.
///
/// - `NYX_CORE_EXE`: otro ejecutable (pruebas).
/// - El núcleo empaquetado junto a la app (9.07, `core/scripts/package_core.py`):
///   `core\python\python.exe -I -X utf8 -m nyx`, sin `uv` (`-I`: sin variables de entorno ni
///   la carpeta del usuario; dónde busca lo fija `python314._pth`).
/// - Si no, `uv run` sobre `NYX_CORE_DIR` o la carpeta `core/` del repositorio (desarrollo).
/// - `NYX_DEMO=1` añade `--demo` (recorre los estados sin voz) en compilaciones de depuración.
fn core_command() -> Command {
    let mut cmd = if let Ok(exe) = std::env::var("NYX_CORE_EXE") {
        Command::new(exe)
    } else if let Some(python) = packaged_python() {
        let mut c = Command::new(python);
        c.args(["-I", "-X", "utf8", "-m", "nyx"]);
        c
    } else {
        let dir = std::env::var("NYX_CORE_DIR")
            .map(PathBuf::from)
            .unwrap_or_else(|_| PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../core"));
        let mut c = Command::new("uv");
        c.arg("run").arg("--project").arg(dir).arg("nyx");
        c
    };
    cmd.arg("--parent-pipe");
    if cfg!(debug_assertions) && std::env::var("NYX_DEMO").as_deref() == Ok("1") {
        cmd.arg("--demo");
    }
    cmd
}

/// El Python del núcleo empaquetado, si la app se ha instalado con él al lado.
fn packaged_python() -> Option<PathBuf> {
    let exe = std::env::current_exe().ok()?;
    let python = exe.parent()?.join("core").join("python").join("python.exe");
    python.is_file().then_some(python)
}
