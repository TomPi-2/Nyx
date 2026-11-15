//! Grabadora de la voz de Nyx (decisión del usuario, 2026-11-15).
//!
//! Para quien pone la voz, que no tiene por qué saber de ordenadores: un solo `.exe`, la
//! frase en grande, botones grandes y avisos en palabras sencillas. El usuario dirige por
//! Discord (repetir, entonación). Todo queda en `Documentos\Voz de Nyx`:
//!
//! ```text
//! Voz de Nyx\
//!   progreso.json                 por dónde iba (sesión, frase, micrófono)
//!   sesion-01\s01-001.wav         la toma buena de cada frase (WAV mono de 24 bits)
//!   sesion-01\descartadas\…       las anteriores (nunca se borra nada)
//!   sesion-01\tomas.jsonl         cada toma con su análisis (para limpiar después)
//!   Para enviar\sesion-01.zip     lo que se manda (WeTransfer o Drive)
//! ```
//!
//! Los audios son suyos y de Nyx, con todos los derechos reservados (contrato): no pasan por
//! ningún servicio de internet desde aquí.

mod audio;

use std::fs;
use std::io::Write;
use std::path::{Path, PathBuf};
use std::sync::Mutex;

use serde::{Deserialize, Serialize};
use tauri::State;
use tauri::ipc::Response;

use audio::{Analysis, Capture, Status};

#[derive(Default)]
struct App {
    capture: Mutex<Option<Capture>>,
}

/// Por dónde iba (se guarda al cambiar de frase).
#[derive(Default, Serialize, Deserialize, Clone)]
struct Progress {
    sesion: u32,
    frase: u32,
    mic: Option<String>,
}

#[derive(Serialize)]
struct Mics {
    names: Vec<String>,
    default: Option<String>,
}

#[derive(Serialize)]
struct Saved {
    analysis: Analysis,
    takes: u32,
}

fn root() -> Result<PathBuf, String> {
    let docs = dirs::document_dir().ok_or("No encuentro tu carpeta Documentos")?;
    let dir = docs.join("Voz de Nyx");
    fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
    Ok(dir)
}

fn session_dir(sesion: u32) -> Result<PathBuf, String> {
    let dir = root()?.join(format!("sesion-{sesion:02}"));
    fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
    Ok(dir)
}

/// Solo letras, números y guiones: el id viene del guion, pero nunca se fía de una ruta.
fn safe_id(id: &str) -> Result<&str, String> {
    if !id.is_empty() && id.len() < 32 && id.chars().all(|c| c.is_ascii_alphanumeric() || c == '-')
    {
        Ok(id)
    } else {
        Err("frase no válida".into())
    }
}

#[tauri::command]
fn mics() -> Mics {
    let (names, default) = audio::mics();
    Mics { names, default }
}

#[tauri::command]
fn load_progress() -> Progress {
    root()
        .ok()
        .and_then(|r| fs::read_to_string(r.join("progreso.json")).ok())
        .and_then(|t| serde_json::from_str(&t).ok())
        .unwrap_or(Progress {
            sesion: 1,
            frase: 0,
            mic: None,
        })
}

#[tauri::command]
fn save_progress(progress: Progress) -> Result<(), String> {
    let text = serde_json::to_string_pretty(&progress).map_err(|e| e.to_string())?;
    fs::write(root()?.join("progreso.json"), text).map_err(|e| e.to_string())
}

#[tauri::command]
fn start(app: State<'_, App>, mic: Option<String>) -> Result<(), String> {
    let mut slot = app.capture.lock().map_err(|e| e.to_string())?;
    if let Some(old) = slot.take() {
        old.finish();
    }
    *slot = Some(Capture::start(mic)?);
    Ok(())
}

#[tauri::command]
fn status(app: State<'_, App>) -> Option<Status> {
    app.capture.lock().ok()?.as_ref().map(Capture::status)
}

/// Para sin guardar (se ha pulsado por error, o se sale).
#[tauri::command]
fn cancel(app: State<'_, App>) {
    if let Ok(mut slot) = app.capture.lock()
        && let Some(c) = slot.take()
    {
        c.finish();
    }
}

/// Para y guarda la toma como la buena de esa frase; la anterior pasa a `descartadas`.
#[tauri::command]
fn stop(app: State<'_, App>, sesion: u32, id: String, texto: String) -> Result<Saved, String> {
    let capture = app
        .capture
        .lock()
        .map_err(|e| e.to_string())?
        .take()
        .ok_or("No estaba grabando")?;
    let (samples, rate) = capture.finish();
    let id = safe_id(&id)?;
    let analysis = audio::analyze(&samples, rate);
    let dir = session_dir(sesion)?;
    let path = dir.join(format!("{id}.wav"));
    let takes = keep_old(&dir, id, &path)?;
    audio::write_wav(&path, &samples, rate)?;
    let line = serde_json::json!({
        "id": id, "texto": texto, "toma": takes + 1, "frecuencia": rate, "analisis": analysis,
    });
    let mut log = fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(dir.join("tomas.jsonl"))
        .map_err(|e| e.to_string())?;
    writeln!(log, "{line}").map_err(|e| e.to_string())?;
    Ok(Saved {
        analysis,
        takes: takes + 1,
    })
}

/// Si ya había una toma de esta frase, se guarda en `descartadas` (nunca se borra nada).
/// Devuelve cuántas había antes.
fn keep_old(dir: &Path, id: &str, path: &Path) -> Result<u32, String> {
    let old = dir.join("descartadas");
    let count = fs::read_dir(&old)
        .map(|it| {
            it.filter_map(Result::ok)
                .filter(|e| {
                    e.file_name()
                        .to_string_lossy()
                        .starts_with(&format!("{id}-"))
                })
                .count() as u32
        })
        .unwrap_or(0);
    if path.exists() {
        fs::create_dir_all(&old).map_err(|e| e.to_string())?;
        fs::rename(path, old.join(format!("{id}-{}.wav", count + 1))).map_err(|e| e.to_string())?;
        return Ok(count + 1);
    }
    Ok(count)
}

/// La toma buena de una frase, para escucharla.
#[tauri::command]
fn take_audio(sesion: u32, id: String) -> Result<Response, String> {
    let id = safe_id(&id)?;
    let bytes = fs::read(session_dir(sesion)?.join(format!("{id}.wav")))
        .map_err(|_| "Esta frase aún no está grabada".to_string())?;
    Ok(Response::new(bytes))
}

/// Las frases de la sesión que ya tienen toma.
#[tauri::command]
fn recorded(sesion: u32) -> Vec<String> {
    session_dir(sesion)
        .ok()
        .and_then(|d| fs::read_dir(d).ok())
        .map(|it| {
            it.filter_map(Result::ok)
                .filter_map(|e| {
                    let name = e.file_name().to_string_lossy().to_string();
                    name.strip_suffix(".wav").map(str::to_string)
                })
                .collect()
        })
        .unwrap_or_default()
}

/// Mete la sesión en un `.zip` (las tomas buenas y su registro) y lo enseña en el Explorador.
#[tauri::command]
fn pack(sesion: u32) -> Result<String, String> {
    let dir = session_dir(sesion)?;
    let out_dir = root()?.join("Para enviar");
    fs::create_dir_all(&out_dir).map_err(|e| e.to_string())?;
    let out = out_dir.join(format!("sesion-{sesion:02}.zip"));
    let file = fs::File::create(&out).map_err(|e| e.to_string())?;
    let mut zip = zip::ZipWriter::new(file);
    // Los WAV ya ocupan lo que ocupan: comprimirlos apenas gana y tarda.
    let stored =
        zip::write::SimpleFileOptions::default().compression_method(zip::CompressionMethod::Stored);
    let mut files = 0;
    for entry in fs::read_dir(&dir).map_err(|e| e.to_string())?.flatten() {
        let path = entry.path();
        let name = entry.file_name().to_string_lossy().to_string();
        if path.is_file() && (name.ends_with(".wav") || name == "tomas.jsonl") {
            zip.start_file(format!("sesion-{sesion:02}/{name}"), stored)
                .map_err(|e| e.to_string())?;
            zip.write_all(&fs::read(&path).map_err(|e| e.to_string())?)
                .map_err(|e| e.to_string())?;
            files += 1;
        }
    }
    zip.finish().map_err(|e| e.to_string())?;
    if files == 0 {
        return Err("Esta sesión aún no tiene nada grabado".into());
    }
    reveal(&out);
    Ok(out.display().to_string())
}

#[tauri::command]
fn open_folder() -> Result<(), String> {
    let dir = root()?;
    std::process::Command::new("explorer")
        .arg(&dir)
        .spawn()
        .map_err(|e| e.to_string())?;
    Ok(())
}

fn reveal(path: &Path) {
    let _ = std::process::Command::new("explorer")
        .arg(format!("/select,{}", path.display()))
        .spawn();
}

pub fn run() {
    tauri::Builder::default()
        .manage(App::default())
        .invoke_handler(tauri::generate_handler![
            mics,
            load_progress,
            save_progress,
            start,
            status,
            cancel,
            stop,
            take_audio,
            recorded,
            pack,
            open_folder,
        ])
        .run(tauri::generate_context!())
        .expect("no se pudo abrir la grabadora");
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn ids_are_never_paths() {
        assert!(safe_id("s01-001").is_ok());
        assert!(safe_id("../x").is_err());
        assert!(safe_id("").is_err());
        assert!(safe_id("a\\b").is_err());
    }

    #[test]
    fn old_takes_are_kept() {
        let dir = std::env::temp_dir().join("grabadora-tomas");
        let _ = fs::create_dir_all(&dir);
        let path = dir.join("s01-001.wav");
        fs::write(&path, b"1").unwrap();
        let before = keep_old(&dir, "s01-001", &path).unwrap();
        assert!(!path.exists());
        assert!(
            dir.join("descartadas")
                .join(format!("s01-001-{before}.wav"))
                .exists()
        );
    }
}
