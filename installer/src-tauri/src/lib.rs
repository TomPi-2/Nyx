//! Instalador de Nyx (tarea 9.08; prototipo `docs/prototipos/instalador.html`, aprobado el
//! 2026-11-14).
//!
//! Una ventana pequeña sin bordes, sin administrador. Al pulsar «Instalar»:
//!
//! 1. **La app** con Velopack (`TepnyxNyx-win-Setup.exe --silent`): en
//!    `%LOCALAPPDATA%\TepnyxNyx` (no en `%LOCALAPPDATA%\Nyx`, que son los datos: desinstalar
//!    Velopack borra su carpeta entera). El Setup se toma del lado del instalador o se
//!    descarga de las Releases oficiales, comprobado con `SHA256SUMS.txt`.
//! 2. Lo elegido en «Opciones»: Everything (lo instala Nyx en el primer arranque, con
//!    `%APPDATA%\Nyx\instalador.json`), arrancar con Windows y el acceso directo.
//! 3. **El oído y la voz** con el propio núcleo (`python -m nyx --download-models --json`): las
//!    mismas descargas, con su SHA-256, que usa Nyx.
//! 4. Abre Nyx: el primer arranque lo guía ella, y Ollama y el cerebro bajan en su panel de
//!    descargas arriba a la derecha, hacia donde se recoge esta ventana.

use std::path::{Path, PathBuf};
use std::process::Stdio;

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use tauri::{AppHandle, Emitter, Manager};
use tokio::io::{AsyncBufReadExt, BufReader};

mod win;

/// Lo que publica `vpk pack` (scripts/build-release.ps1): mismo identificador y ejecutable.
const PACK_ID: &str = "TepnyxNyx";
const MAIN_EXE: &str = "nyx-ui.exe";
const SETUP_NAME: &str = "TepnyxNyx-win-Setup.exe";
/// Releases oficiales (HTTPS). Solo de aquí se descarga.
const RELEASES: &str = "https://github.com/TomPi-2/Nyx/releases/latest/download";
const LICENSE_URL: &str = "https://www.gnu.org/licenses/gpl-3.0.html";
const MB: f64 = 1_000_000.0;

#[derive(Deserialize)]
struct Options {
    everything: bool,
    autostart: bool,
    shortcut: bool,
}

/// Avance de una parte («app», o una descarga del núcleo: «stt», «pocket»…).
#[derive(Clone, Serialize, Deserialize)]
struct Progress {
    key: String,
    label: String,
    done_mb: f64,
    total_mb: f64,
    finished: bool,
    error: Option<String>,
}

fn emit(app: &AppHandle, p: Progress) {
    let _ = app.emit("install://progress", p);
}

fn local_appdata() -> Result<PathBuf, String> {
    std::env::var_os("LOCALAPPDATA")
        .map(PathBuf::from)
        .ok_or_else(|| "sin LOCALAPPDATA".to_string())
}

fn install_dir() -> Result<PathBuf, String> {
    Ok(local_appdata()?.join(PACK_ID))
}

/// Espacio libre (GB) en la unidad donde se instala.
#[tauri::command]
fn disk_free_gb() -> Option<f64> {
    win::free_bytes(&local_appdata().ok()?).map(|b| b as f64 / 1e9)
}

#[tauri::command]
fn open_license() {
    win::open_url(LICENSE_URL);
}

#[tauri::command]
async fn install(app: AppHandle, options: Options) -> Result<(), String> {
    // 1. La app.
    let progress = |done: f64, total: f64, finished: bool, error: Option<String>| Progress {
        key: "app".into(),
        label: "Nyx".into(),
        done_mb: done,
        total_mb: total,
        finished,
        error,
    };
    emit(&app, progress(0.0, 1.0, false, None));
    let setup = match find_setup(&app) {
        Some(path) => path,
        None => download_setup(&app).await.inspect_err(|e| {
            emit(&app, progress(0.0, 1.0, true, Some(e.clone())));
        })?,
    };
    let status = tokio::process::Command::new(&setup)
        .arg("--silent")
        // La app que abre el Setup al acabar se cierra sola: la abre este instalador después
        // de bajar el oído y la voz (main.rs de la app, `on_first_run`).
        .env("NYX_INSTALLER", "1")
        .status()
        .await
        .map_err(|e| format!("no se pudo instalar: {e}"))?;
    let stub = install_dir()?.join(MAIN_EXE);
    if !status.success() || !stub.is_file() {
        let error = format!("la instalación ha fallado ({status})");
        emit(&app, progress(0.0, 1.0, true, Some(error.clone())));
        return Err(error);
    }
    emit(&app, progress(1.0, 1.0, true, None));

    // 2. Lo elegido.
    write_choices(&options)?;
    if options.autostart {
        win::set_autostart(&stub).map_err(|e| format!("arrancar con Windows: {e}"))?;
    }
    if options.shortcut {
        win::desktop_shortcut(&stub, "Nyx").map_err(|e| format!("acceso directo: {e}"))?;
    }

    // 3. El oído y la voz, con el núcleo recién instalado.
    download_voice(&app).await
}

/// Abre Nyx (el primer arranque lo guía ella) y cierra el instalador.
#[tauri::command]
fn launch_nyx(app: AppHandle) -> Result<(), String> {
    let stub = install_dir()?.join(MAIN_EXE);
    std::process::Command::new(&stub)
        .spawn()
        .map_err(|e| format!("no se pudo abrir Nyx: {e}"))?;
    app.exit(0);
    Ok(())
}

/// El Setup junto al instalador (o en sus recursos): instalación sin internet y pruebas.
fn find_setup(app: &AppHandle) -> Option<PathBuf> {
    let beside = std::env::current_exe().ok()?.parent()?.join(SETUP_NAME);
    let resource = app.path().resource_dir().ok().map(|d| d.join(SETUP_NAME));
    [Some(beside), resource]
        .into_iter()
        .flatten()
        .find(|p| p.is_file())
}

/// Descarga el Setup de la última Release y lo comprueba con `SHA256SUMS.txt`.
async fn download_setup(app: &AppHandle) -> Result<PathBuf, String> {
    let sums = http_text(&format!("{RELEASES}/SHA256SUMS.txt")).await?;
    let expected =
        expected_hash(&sums, SETUP_NAME).ok_or("la Release no trae la huella del instalador")?;
    let dest = std::env::temp_dir().join(SETUP_NAME);
    let url = format!("{RELEASES}/{SETUP_NAME}");
    let app = app.clone();
    let path = dest.clone();
    tauri::async_runtime::spawn_blocking(move || {
        download_to(&url, &path, &expected, |done, total| {
            emit(
                &app,
                Progress {
                    key: "app".into(),
                    label: "Nyx".into(),
                    done_mb: done as f64 / MB,
                    total_mb: total.max(1) as f64 / MB,
                    finished: false,
                    error: None,
                },
            );
        })
    })
    .await
    .map_err(|e| e.to_string())??;
    Ok(dest)
}

/// La huella de `name` en un `SHA256SUMS.txt` («<hash>  <nombre>», o con `*` delante).
fn expected_hash(sums: &str, name: &str) -> Option<String> {
    sums.lines()
        .filter_map(|l| l.split_once(char::is_whitespace))
        .find(|(_, file)| file.trim().trim_start_matches('*') == name)
        .map(|(hash, _)| hash.trim().to_lowercase())
        .filter(|h| h.len() == 64 && h.chars().all(|c| c.is_ascii_hexdigit()))
}

async fn http_text(url: &str) -> Result<String, String> {
    let url = url.to_string();
    tauri::async_runtime::spawn_blocking(move || {
        win::http_get(&url, |_| {})
            .and_then(|bytes| String::from_utf8(bytes).map_err(|e| e.to_string()))
    })
    .await
    .map_err(|e| e.to_string())?
}

fn download_to(
    url: &str,
    dest: &Path,
    sha256: &str,
    progress: impl Fn(u64, u64),
) -> Result<(), String> {
    let bytes = win::http_get(url, |p| progress(p.0, p.1))?;
    let got = hex(&Sha256::digest(&bytes));
    if got != sha256 {
        return Err("la huella del instalador descargado no coincide: no se usa".into());
    }
    std::fs::write(dest, &bytes).map_err(|e| e.to_string())
}

fn hex(bytes: &[u8]) -> String {
    bytes.iter().map(|b| format!("{b:02x}")).collect()
}

fn write_choices(options: &Options) -> Result<(), String> {
    let dir = std::env::var_os("APPDATA")
        .map(PathBuf::from)
        .ok_or("sin APPDATA")?
        .join("Nyx");
    std::fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
    let data = serde_json::json!({ "everything": options.everything });
    std::fs::write(dir.join("instalador.json"), data.to_string()).map_err(|e| e.to_string())
}

/// `python -m nyx --download-models --json` del núcleo instalado: cada línea es un avance.
async fn download_voice(app: &AppHandle) -> Result<(), String> {
    let python = install_dir()?
        .join("current")
        .join("core")
        .join("python")
        .join("python.exe");
    let mut cmd = tokio::process::Command::new(&python);
    cmd.args([
        "-I",
        "-X",
        "utf8",
        "-m",
        "nyx",
        "--download-models",
        "--json",
    ])
    .stdin(Stdio::null())
    .stdout(Stdio::piped())
    .stderr(Stdio::null());
    #[cfg(windows)]
    cmd.creation_flags(0x0800_0000); // CREATE_NO_WINDOW
    let mut child = cmd
        .spawn()
        .map_err(|e| format!("no se pudo preparar la voz: {e}"))?;
    let stdout = child.stdout.take().ok_or("sin salida")?;
    let mut lines = BufReader::new(stdout).lines();
    while let Ok(Some(line)) = lines.next_line().await {
        if let Ok(p) = serde_json::from_str::<Progress>(&line) {
            emit(app, p);
        }
    }
    let status = child.wait().await.map_err(|e| e.to_string())?;
    if status.success() {
        Ok(())
    } else {
        Err("no se ha podido bajar todo el oído y la voz (Nyx lo reintentará al abrirse)".into())
    }
}

pub fn run() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![
            disk_free_gb,
            open_license,
            install,
            launch_nyx
        ])
        .run(tauri::generate_context!())
        .expect("no se pudo abrir el instalador");
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn reads_the_setup_hash() {
        let hash = "a".repeat(64);
        let other = "b".repeat(64);
        let sums = format!("{other}  otro.zip\n{}  {SETUP_NAME}\n", hash.to_uppercase());
        assert_eq!(expected_hash(&sums, SETUP_NAME), Some(hash));
        assert_eq!(expected_hash("xyz  TepnyxNyx-win-Setup.exe", SETUP_NAME), None);
        assert_eq!(expected_hash("", SETUP_NAME), None);
    }

    #[test]
    fn checks_the_download() {
        let dir = std::env::temp_dir();
        let dest = dir.join("nyx-installer-test.bin");
        // Sin red: una URL que no es HTTPS se rechaza antes de descargar.
        assert!(download_to("http://example.com/x", &dest, "00", |_, _| {}).is_err());
        assert_eq!(hex(&[0x0f, 0xa0]), "0fa0");
    }
}
