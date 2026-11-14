//! Actualizaciones automáticas, la parte de la app (SPEC §15; tarea 9.06).
//!
//! Velopack (MIT) desde las Releases de GitHub: comprueba al arrancar y cada 6 h, descarga en
//! segundo plano con prioridad baja (deltas si los hay) y avisa a la isla
//! (`update://ready`), que se lo pasa al núcleo. El núcleo decide cuándo (Preguntar,
//! Automático o Solo avisar, y solo en un buen momento: core/nyx/update/coordinator.py) y pide
//! aplicarla (`update_apply`): se para el núcleo y Velopack cambia de versión y reinicia Nyx.
//! Si se cierra Nyx antes, la versión descargada se aplica sola al volver a abrirla
//! (`VelopackApp`, en main.rs).
//!
//! Sin instalar con Velopack (desarrollo) no hace nada. Mientras el repositorio sea privado,
//! la comprobación falla en silencio (no hay Releases públicas).

use std::sync::Mutex;
use std::time::Duration;

use serde::Serialize;
use tauri::{AppHandle, Emitter, Manager, State};
use tokio::sync::Notify;
use velopack::sources::GithubSource;
use velopack::{UpdateCheck, UpdateInfo, UpdateManager, UpdateOptions};

use crate::core_process;

/// Repositorio oficial: solo de aquí (HTTPS) se descargan versiones.
const REPO: &str = "https://github.com/TomPi-2/Nyx";
const EVERY: Duration = Duration::from_secs(6 * 3600);

#[derive(Default)]
pub struct Updater {
    /// Canal elegido en Ajustes → General (`estable` o `beta`); None hasta que la isla lo dice.
    channel: Mutex<Option<String>>,
    /// Versión ya descargada, lista para aplicar.
    ready: Mutex<Option<UpdateInfo>>,
    changed: Notify,
}

#[derive(Clone, Serialize)]
struct Ready {
    version: String,
}

pub fn init(app: &AppHandle) {
    app.manage(Updater::default());
    let handle = app.clone();
    tauri::async_runtime::spawn(async move { watch(handle).await });
}

/// La isla pasa el canal de Ajustes al conectar y cada vez que cambia.
#[tauri::command]
pub fn update_configure(updater: State<'_, Updater>, channel: String) {
    let channel = if channel == "beta" { "beta" } else { "estable" }.to_string();
    if let Ok(mut current) = updater.channel.lock() {
        if current.as_deref() == Some(channel.as_str()) {
            return;
        }
        *current = Some(channel);
    }
    updater.changed.notify_one();
}

/// El núcleo ha decidido aplicarla ya (o se ha pulsado «Ahora»).
#[tauri::command]
pub async fn update_apply(app: AppHandle) -> Result<(), String> {
    let info = app
        .state::<Updater>()
        .ready
        .lock()
        .map_err(|e| e.to_string())?
        .clone()
        .ok_or("no hay ninguna versión descargada")?;
    let beta = channel(&app) == "beta";
    let manager = manager(beta)?;
    // El núcleo se para antes (sus servicios se cierran al morir: whisper-server, Ollama no).
    core_process::stop(&app).await;
    // Sale de la app; Velopack aplica la versión y vuelve a abrir Nyx.
    manager
        .apply_updates_and_restart(&info)
        .map_err(|e| e.to_string())
}

fn channel(app: &AppHandle) -> String {
    app.state::<Updater>()
        .channel
        .lock()
        .ok()
        .and_then(|c| c.clone())
        .unwrap_or_else(|| "estable".into())
}

fn manager(beta: bool) -> Result<UpdateManager, String> {
    // Beta: también las versiones marcadas como «pre-release» en GitHub.
    let source = GithubSource::new(REPO, None, beta);
    UpdateManager::new(source, Some(UpdateOptions::default()), None).map_err(|e| e.to_string())
}

async fn watch(app: AppHandle) {
    let updater = app.state::<Updater>();
    // Hasta que la isla dice el canal (llegan los ajustes), no se mira nada.
    while updater.channel.lock().map(|c| c.is_none()).unwrap_or(true) {
        updater.changed.notified().await;
    }
    loop {
        let beta = channel(&app) == "beta";
        let found = tauri::async_runtime::spawn_blocking(move || check_and_download(beta))
            .await
            .ok()
            .flatten();
        if let Some(info) = found {
            let version = info.TargetFullRelease.Version.clone();
            if let Ok(mut ready) = updater.ready.lock() {
                *ready = Some(info);
            }
            let _ = app.emit_to("island", "update://ready", Ready { version });
        }
        tokio::select! {
            _ = tokio::time::sleep(EVERY) => {}
            _ = updater.changed.notified() => {}
        }
    }
}

/// Comprueba y descarga (bloqueante: en un hilo aparte, con prioridad baja).
fn check_and_download(beta: bool) -> Option<UpdateInfo> {
    let _background = Background::begin();
    let manager = match manager(beta) {
        Ok(m) => m,
        Err(_) => return None, // sin instalar con Velopack (desarrollo)
    };
    // Ya descargada en otra sesión y sin aplicar.
    if let Some(asset) = manager.get_update_pending_restart() {
        return Some(UpdateInfo {
            TargetFullRelease: asset,
            ..UpdateInfo::default()
        });
    }
    match manager.check_for_updates() {
        Ok(UpdateCheck::UpdateAvailable(info)) => match manager.download_updates(&info, None) {
            Ok(()) => Some(*info),
            Err(err) => {
                eprintln!("[nyx] actualización: no se pudo descargar: {err}");
                None
            }
        },
        Ok(_) => None,
        Err(err) => {
            eprintln!("[nyx] actualización: no se pudo comprobar: {err}");
            None
        }
    }
}

/// Modo de fondo del hilo (CPU, disco y red con prioridad baja) mientras dura.
struct Background;

impl Background {
    fn begin() -> Background {
        #[cfg(windows)]
        // SAFETY: cambia la prioridad del hilo actual; se deshace en Drop en el mismo hilo.
        unsafe {
            use windows::Win32::System::Threading::{
                GetCurrentThread, SetThreadPriority, THREAD_MODE_BACKGROUND_BEGIN,
            };
            let _ = SetThreadPriority(GetCurrentThread(), THREAD_MODE_BACKGROUND_BEGIN);
        }
        Background
    }
}

impl Drop for Background {
    fn drop(&mut self) {
        #[cfg(windows)]
        // SAFETY: ver `begin`.
        unsafe {
            use windows::Win32::System::Threading::{
                GetCurrentThread, SetThreadPriority, THREAD_MODE_BACKGROUND_END,
            };
            let _ = SetThreadPriority(GetCurrentThread(), THREAD_MODE_BACKGROUND_END);
        }
    }
}
