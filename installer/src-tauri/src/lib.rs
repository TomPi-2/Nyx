//! Instalador de Nyx (tarea 9.08; prototipo `docs/prototipos/instalador.html`, aprobado el
//! 2026-11-14).
//!
//! Una ventana pequeña sin bordes, sin administrador, con el cristal de la app
//! (`crates/nyx-glass`) si la tarjeta gráfica puede. Al pulsar «Instalar»:
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
//!
//! Cada fallo lleva un código (`docs/CODIGOS-DE-ERROR.md`, «I-…») que se enseña con un
//! enlace a su explicación en la web.

use std::path::{Path, PathBuf};
use std::process::Stdio;

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use tauri::{AppHandle, Emitter, Manager, Runtime, State, WebviewWindow};
use tokio::io::{AsyncBufReadExt, BufReader};

use nyx_glass::{Engine, GlassOptions, Shape};

mod in_use;
mod win;

/// Lo que publica `vpk pack` (scripts/build-release.ps1). Velopack deja en la carpeta un
/// lanzador con el nombre de la app (`--packTitle Nyx`): `Nyx.exe`, que abre siempre la
/// versión actual. (Buscar `nyx-ui.exe` ahí fue el fallo de la primera prueba: estaba
/// instalada y decía que no.)
const PACK_ID: &str = "TepnyxNyx";
const LAUNCHER: &str = "Nyx.exe";
const SETUP_NAME: &str = "TepnyxNyx-win-Setup.exe";
/// Releases oficiales (HTTPS). Solo de aquí se descarga.
const RELEASES: &str = "https://github.com/TomPi-2/Nyx/releases/latest/download";
const LICENSE_URL: &str = "https://www.gnu.org/licenses/gpl-3.0.html";
/// La explicación de cada código de error (con su ancla: `#I-110`).
const ERRORS_URL: &str = "https://tepnyx.com/nyx/errores";
const MB: f64 = 1_000_000.0;

/// Un fallo para el usuario: el código (para buscarlo en la web), qué ha pasado en sus
/// palabras y el detalle técnico (para el registro y para quien ayude).
#[derive(Debug, Clone, Serialize)]
struct Fail {
    code: &'static str,
    message: &'static str,
    detail: String,
}

fn fail(code: &'static str, message: &'static str, detail: impl ToString) -> Fail {
    Fail {
        code,
        message,
        detail: detail.to_string(),
    }
}

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

fn app_progress(done: f64, total: f64, finished: bool, error: Option<String>) -> Progress {
    Progress {
        key: "app".into(),
        label: "Nyx".into(),
        done_mb: done,
        total_mb: total,
        finished,
        error,
    }
}

/// Lo que contó la descarga del oído y la voz, para saber qué falló (no hay otra forma de
/// verlo: el instalador no abre consolas). Se añade al final de `logs\instalador.log`.
fn write_log(output: &str, errors: &[String]) {
    use std::io::Write;
    let Some(dir) = local_appdata().map(|d| d.join("Nyx").join("logs")) else {
        return;
    };
    if std::fs::create_dir_all(&dir).is_err() {
        return;
    }
    let Ok(mut file) = std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(dir.join("instalador.log"))
    else {
        return;
    };
    let stamp = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0);
    let _ = writeln!(
        file,
        "--- Instalador {} · oído y voz (unix {stamp})",
        env!("CARGO_PKG_VERSION")
    );
    let _ = file.write_all(output.as_bytes());
    for error in errors {
        let _ = writeln!(file, "Error: {error}");
    }
}

fn local_appdata() -> Option<PathBuf> {
    std::env::var_os("LOCALAPPDATA").map(PathBuf::from)
}

fn install_dir() -> Result<PathBuf, Fail> {
    local_appdata().map(|d| d.join(PACK_ID)).ok_or_else(|| {
        fail(
            "I-111",
            "No encuentro tu carpeta de usuario",
            "sin LOCALAPPDATA",
        )
    })
}

/// Espacio libre (GB) en la unidad donde se instala.
#[tauri::command]
fn disk_free_gb() -> Option<f64> {
    win::free_bytes(&local_appdata()?).map(|b| b as f64 / 1e9)
}

#[tauri::command]
fn open_license() {
    win::open_url(LICENSE_URL);
}

/// Abre la explicación de un código de error en la web.
#[tauri::command]
fn open_error(code: String) {
    let code: String = code
        .chars()
        .filter(|c| c.is_ascii_alphanumeric() || *c == '-')
        .collect();
    win::open_url(&format!("{ERRORS_URL}#{code}"));
}

#[tauri::command]
async fn install(app: AppHandle, options: Options) -> Result<(), Fail> {
    let result = install_steps(&app, &options).await;
    if let Err(f) = &result {
        eprintln!("[instalador] {} {}: {}", f.code, f.message, f.detail);
        emit(&app, app_progress(0.0, 1.0, true, Some(f.code.to_string())));
    }
    result
}

async fn install_steps(app: &AppHandle, options: &Options) -> Result<(), Fail> {
    // 1. La app.
    emit(app, app_progress(0.0, 1.0, false, None));
    let setup = match find_setup(app) {
        Some(path) => path,
        None => download_setup(app).await?,
    };
    // Si ya hay una Nyx instalada (la misma versión u otra), el Setup la sustituye.
    let before = in_use::log_len();
    let mut status = run_setup(&setup).await?;
    if !status.success() && in_use::folder_in_use(before) {
        // Algo de fuera tiene abierta la carpeta de la Nyx que hay (Ollama o Everything):
        // se cierran, se reintenta y se vuelven a abrir como estaban.
        let stopped = tokio::task::spawn_blocking(in_use::stop_helpers)
            .await
            .unwrap_or_default();
        tokio::time::sleep(std::time::Duration::from_millis(1500)).await;
        let again = in_use::log_len();
        status = run_setup(&setup).await?;
        in_use::relaunch(&stopped);
        if !status.success() && in_use::folder_in_use(again) {
            let closed = in_use::names(&stopped);
            return Err(fail(
                "I-113",
                "Algo tiene abierta la carpeta de Nyx",
                format!("{status}; cerrado: {closed}"),
            ));
        }
    }
    if !status.success() {
        return Err(fail("I-110", "La instalación de Nyx ha fallado", status));
    }
    let launcher = install_dir()?.join(LAUNCHER);
    if !launcher.is_file() {
        return Err(fail(
            "I-111",
            "Nyx se ha instalado pero no la encuentro",
            launcher.display(),
        ));
    }
    emit(app, app_progress(1.0, 1.0, true, None));

    // 2. Lo elegido. Si algo de esto falla, Nyx funciona igual: se apunta y se sigue.
    if let Err(e) = write_choices(options) {
        eprintln!("[instalador] I-120: {e}");
    }
    if options.autostart
        && let Err(e) = win::set_autostart(&launcher)
    {
        eprintln!("[instalador] I-121: {e}");
    }
    if options.shortcut
        && let Err(e) = win::desktop_shortcut(&launcher, "Nyx")
    {
        eprintln!("[instalador] I-122: {e}");
    }

    // 3. El oído y la voz, con el núcleo recién instalado.
    download_voice(app).await
}

/// El Setup de Velopack en silencio.
async fn run_setup(setup: &std::path::Path) -> Result<std::process::ExitStatus, Fail> {
    tokio::process::Command::new(setup)
        .arg("--silent")
        // La app que abre el Setup al acabar se cierra sola: la abre este instalador después
        // de bajar el oído y la voz (install_hooks.rs de la app).
        .env("NYX_INSTALLER", "1")
        .status()
        .await
        .map_err(|e| fail("I-112", "No he podido abrir el instalador de Nyx", e))
}

/// Abre Nyx (el primer arranque lo guía ella) y cierra el instalador.
#[tauri::command]
fn launch_nyx(app: AppHandle) -> Result<(), Fail> {
    let launcher = install_dir()?.join(LAUNCHER);
    std::process::Command::new(&launcher)
        .spawn()
        .map_err(|e| fail("I-140", "Nyx está instalada pero no he podido abrirla", e))?;
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
async fn download_setup(app: &AppHandle) -> Result<PathBuf, Fail> {
    let sums = http_text(&format!("{RELEASES}/SHA256SUMS.txt"))
        .await
        .map_err(|e| fail("I-101", "No he podido descargar Nyx", e))?;
    let expected = expected_hash(&sums, SETUP_NAME).ok_or_else(|| {
        fail(
            "I-103",
            "La versión publicada no trae su huella",
            "SHA256SUMS.txt sin el Setup",
        )
    })?;
    let dest = std::env::temp_dir().join(SETUP_NAME);
    let url = format!("{RELEASES}/{SETUP_NAME}");
    let app = app.clone();
    let path = dest.clone();
    tauri::async_runtime::spawn_blocking(move || {
        download_to(&url, &path, &expected, |done, total| {
            emit(
                &app,
                app_progress(done as f64 / MB, total.max(1) as f64 / MB, false, None),
            );
        })
    })
    .await
    .map_err(|e| fail("I-101", "No he podido descargar Nyx", e))??;
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
) -> Result<(), Fail> {
    let bytes = win::http_get(url, |p| progress(p.0, p.1))
        .map_err(|e| fail("I-101", "No he podido descargar Nyx", e))?;
    let got = hex(&Sha256::digest(&bytes));
    if got != sha256 {
        return Err(fail(
            "I-102",
            "Lo descargado no coincide con su huella: no lo uso",
            format!("esperada {sha256}, obtenida {got}"),
        ));
    }
    std::fs::write(dest, &bytes).map_err(|e| fail("I-101", "No he podido guardar Nyx", e))
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
async fn download_voice(app: &AppHandle) -> Result<(), Fail> {
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
    // Lo que cuenta la descarga (y sus errores) va a `logs\instalador.log`: sin él no se sabía
    // por qué fallaba (I-131 de un tester, 2026-11-18).
    .stderr(Stdio::piped());
    #[cfg(windows)]
    cmd.creation_flags(0x0800_0000); // CREATE_NO_WINDOW
    let mut child = cmd
        .spawn()
        .map_err(|e| fail("I-130", "No he podido preparar el oído y la voz", e))?;
    let stdout = child.stdout.take().ok_or_else(|| {
        fail(
            "I-130",
            "No he podido preparar el oído y la voz",
            "sin salida",
        )
    })?;
    let stderr = child.stderr.take();
    let log = tokio::spawn(async move {
        let mut text = String::new();
        if let Some(stderr) = stderr {
            let mut lines = BufReader::new(stderr).lines();
            while let Ok(Some(line)) = lines.next_line().await {
                text.push_str(&line);
                text.push('\n');
            }
        }
        text
    });
    let mut errors: Vec<String> = Vec::new();
    let mut lines = BufReader::new(stdout).lines();
    while let Ok(Some(line)) = lines.next_line().await {
        if let Ok(p) = serde_json::from_str::<Progress>(&line) {
            if let Some(error) = &p.error {
                errors.push(error.clone());
            }
            emit(app, p);
        }
    }
    let status = child
        .wait()
        .await
        .map_err(|e| fail("I-130", "No he podido preparar el oído y la voz", e))?;
    let output = log.await.unwrap_or_default();
    write_log(&output, &errors);
    if status.success() {
        Ok(())
    } else {
        let detail = if errors.is_empty() {
            format!("{status} · más en %LOCALAPPDATA%\\Nyx\\logs\\instalador.log")
        } else {
            errors.join(" · ")
        };
        Err(fail(
            "I-131",
            "No he podido bajar todo el oído y la voz (Nyx lo reintentará al abrirse)",
            detail,
        ))
    }
}

// --- Cristal (el mismo motor que la app) -------------------------------------------------

#[tauri::command]
fn glass_attach<R: Runtime>(
    window: WebviewWindow<R>,
    engine: State<'_, Engine>,
    options: GlassOptions,
) -> Result<(), String> {
    engine.attach(&window, options)
}

#[tauri::command]
fn glass_set_options<R: Runtime>(
    window: WebviewWindow<R>,
    engine: State<'_, Engine>,
    options: GlassOptions,
) {
    engine.set_options(window.label(), options);
}

#[tauri::command]
fn glass_set_shapes<R: Runtime>(
    window: WebviewWindow<R>,
    engine: State<'_, Engine>,
    shapes: Vec<Shape>,
) {
    engine.set_shapes(window.label(), shapes);
}

#[tauri::command]
fn glass_poke<R: Runtime>(window: WebviewWindow<R>, engine: State<'_, Engine>) {
    engine.poke(window.label());
}

#[tauri::command]
fn glass_detach<R: Runtime>(window: WebviewWindow<R>, engine: State<'_, Engine>) {
    engine.detach(window.label());
}

#[tauri::command]
fn glass_set_game(engine: State<'_, Engine>, active: bool) {
    engine.set_game(active);
}

pub fn run() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![
            disk_free_gb,
            open_license,
            open_error,
            install,
            launch_nyx,
            glass_attach,
            glass_set_options,
            glass_set_shapes,
            glass_poke,
            glass_detach,
            glass_set_game,
        ])
        .setup(|app| {
            nyx_glass::init(app.handle());
            Ok(())
        })
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
        assert_eq!(
            expected_hash("xyz  TepnyxNyx-win-Setup.exe", SETUP_NAME),
            None
        );
        assert_eq!(expected_hash("", SETUP_NAME), None);
    }

    #[test]
    fn download_errors_carry_their_code() {
        let dest = std::env::temp_dir().join("nyx-installer-test.bin");
        // Sin red: una URL que no es HTTPS se rechaza antes de descargar.
        let err = download_to("http://example.com/x", &dest, "00", |_, _| {}).unwrap_err();
        assert_eq!(err.code, "I-101");
        assert_eq!(hex(&[0x0f, 0xa0]), "0fa0");
    }

    #[test]
    fn every_code_is_in_the_catalog() {
        let catalog = include_str!("../../../docs/CODIGOS-DE-ERROR.md");
        let source = include_str!("lib.rs");
        let mut found = 0;
        for (i, _) in source.match_indices("\"I-") {
            let code = &source[i + 1..i + 6];
            if !code[2..].chars().all(|c| c.is_ascii_digit()) {
                continue;
            }
            assert!(
                catalog.contains(&format!("| {code} |")),
                "{code} no está en el catálogo"
            );
            found += 1;
        }
        assert!(found >= 8);
    }
}
