//! Vuelta atrás automática (SPEC §15, paso 6): si una versión nueva no arranca, se vuelve a
//! la anterior. Velopack no la trae; se hace así:
//!
//! 1. **Antes de aplicar** una versión (updater.rs), se copia el paquete completo de la actual
//!    (`…\TepnyxNyx\packages\TepnyxNyx-<versión>-full.nupkg`) a
//!    `%LOCALAPPDATA%\Nyx\copias\app\` con un índice propio (`releases.win.json`, con su
//!    SHA-256) y se apunta el cambio en `cambio.json` («pendiente: de X a Y»).
//! 2. **Al arrancar la nueva**: si el núcleo dice «listo» en 90 s, queda confirmada. Si no, o
//!    si el núcleo se cae tres veces seguidas (core_process.rs), se vuelve: Velopack lee la
//!    copia como origen de actualizaciones (`FileSource`, permitiendo bajar de versión), la
//!    aplica y reinicia Nyx.
//! 3. **Ya en la anterior**, se avisa con el código A-304.

use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, Ordering};
use std::time::Duration;

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use tauri::{AppHandle, Listener};
use velopack::sources::FileSource;
use velopack::{UpdateCheck, UpdateManager, UpdateOptions};

use crate::{core_process, errors};

const PACK_ID: &str = "TepnyxNyx";
const CHANNEL: &str = "win";
/// Lo que se da a la versión nueva para que el núcleo diga «listo».
const READY_WITHIN: Duration = Duration::from_secs(90);

static ROLLING_BACK: AtomicBool = AtomicBool::new(false);

#[derive(Serialize, Deserialize, Clone, Debug, PartialEq)]
struct Change {
    de: String,
    a: String,
    /// «pendiente» (recién aplicada), «ok», «vuelta» (se volvió) o «avisado».
    estado: String,
}

fn backup_dir() -> Option<PathBuf> {
    Some(
        PathBuf::from(std::env::var_os("LOCALAPPDATA")?)
            .join("Nyx")
            .join("copias")
            .join("app"),
    )
}

/// Carpeta de Velopack (`…\TepnyxNyx`) si la app está instalada con él.
fn install_root() -> Option<PathBuf> {
    let root = std::env::current_exe()
        .ok()?
        .parent()?
        .parent()?
        .to_path_buf();
    root.join("Update.exe").is_file().then_some(root)
}

fn read_change(dir: &Path) -> Option<Change> {
    serde_json::from_str(&std::fs::read_to_string(dir.join("cambio.json")).ok()?).ok()
}

fn write_change(dir: &Path, change: &Change) {
    if let Ok(text) = serde_json::to_string_pretty(change) {
        let _ = std::fs::write(dir.join("cambio.json"), text);
    }
}

/// Antes de aplicar `to`: copia del paquete de la versión actual (`from`) para poder volver.
pub fn before_apply(from: &str, to: &str) -> Result<(), String> {
    let root = install_root().ok_or("sin instalar con Velopack")?;
    let dir = backup_dir().ok_or("sin LOCALAPPDATA")?;
    std::fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
    let name = format!("{PACK_ID}-{from}-full.nupkg");
    let source = root.join("packages").join(&name);
    if !source.is_file() {
        return Err(format!("no está el paquete de la {from}"));
    }
    // Siempre el mismo nombre de copia: se sustituye la de la vez anterior (es solo nuestra).
    let copy = dir.join(format!("{PACK_ID}-anterior-full.nupkg"));
    std::fs::copy(&source, &copy).map_err(|e| e.to_string())?;
    let bytes = std::fs::read(&copy).map_err(|e| e.to_string())?;
    let feed = feed(from, &copy, &bytes);
    std::fs::write(dir.join(format!("releases.{CHANNEL}.json")), feed)
        .map_err(|e| e.to_string())?;
    write_change(
        &dir,
        &Change {
            de: from.into(),
            a: to.into(),
            estado: "pendiente".into(),
        },
    );
    Ok(())
}

/// El índice que lee `FileSource`: un solo paquete completo, con su tamaño y SHA-256.
fn feed(version: &str, file: &Path, bytes: &[u8]) -> String {
    let sha256: String = Sha256::digest(bytes)
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect();
    serde_json::json!({
        "Assets": [{
            "PackageId": PACK_ID,
            "Version": version,
            "Type": "Full",
            "FileName": file.file_name().map(|n| n.to_string_lossy().to_string()).unwrap_or_default(),
            "SHA1": "",
            "SHA256": sha256,
            "Size": bytes.len() as u64,
            "NotesMarkdown": "",
            "NotesHtml": "",
        }]
    })
    .to_string()
}

/// Al arrancar: si se acaba de aplicar una versión, vigila que arranque; si se acaba de
/// volver atrás, lo dice.
pub fn check(app: &AppHandle) {
    let Some(dir) = backup_dir() else { return };
    let Some(change) = read_change(&dir) else {
        return;
    };
    let current = app.package_info().version.to_string();
    if change.estado == "vuelta" && current == change.de {
        errors::notify(
            app,
            errors::UPDATE_ROLLED_BACK,
            "He vuelto a la versión anterior",
            &format!(
                "La {} no arrancaba bien; sigo con la {}.",
                change.a, change.de
            ),
        );
        write_change(
            &dir,
            &Change {
                estado: "avisado".into(),
                ..change
            },
        );
        return;
    }
    if change.estado != "pendiente" || current != change.a {
        return;
    }
    let confirmed = std::sync::Arc::new(AtomicBool::new(false));
    let flag = confirmed.clone();
    let ok_dir = dir.clone();
    let ok_change = change.clone();
    app.once("core://ready", move |_| {
        flag.store(true, Ordering::SeqCst);
        write_change(
            &ok_dir,
            &Change {
                estado: "ok".into(),
                ..ok_change
            },
        );
    });
    let handle = app.clone();
    tauri::async_runtime::spawn(async move {
        tokio::time::sleep(READY_WITHIN).await;
        if !confirmed.load(Ordering::SeqCst) {
            roll_back(&handle).await;
        }
    });
}

/// ¿Está pendiente de confirmar una versión recién aplicada? (core_process.rs: si el núcleo se
/// cae tres veces seguidas mientras tanto, se vuelve.)
pub fn pending(app: &AppHandle) -> bool {
    let current = app.package_info().version.to_string();
    backup_dir()
        .and_then(|d| read_change(&d))
        .is_some_and(|c| c.estado == "pendiente" && c.a == current)
}

/// Vuelve a la versión de la copia y reinicia Nyx.
pub async fn roll_back(app: &AppHandle) {
    if ROLLING_BACK.swap(true, Ordering::SeqCst) {
        return;
    }
    let Some(dir) = backup_dir() else { return };
    let Some(change) = read_change(&dir) else {
        return;
    };
    eprintln!(
        "[nyx] {}: la {} no arranca; vuelvo a la {}",
        errors::UPDATE_ROLLED_BACK,
        change.a,
        change.de
    );
    let source_dir = dir.clone();
    let found = tauri::async_runtime::spawn_blocking(move || {
        let options = UpdateOptions {
            AllowVersionDowngrade: true,
            ExplicitChannel: Some(CHANNEL.into()),
            ..UpdateOptions::default()
        };
        let manager = UpdateManager::new(FileSource::new(&source_dir), Some(options), None).ok()?;
        match manager.check_for_updates().ok()? {
            UpdateCheck::UpdateAvailable(info) => {
                manager.download_updates(&info, None).ok()?;
                Some((manager, *info))
            }
            _ => None,
        }
    })
    .await
    .ok()
    .flatten();
    let Some((manager, info)) = found else {
        eprintln!("[nyx] no he podido volver a la {}", change.de);
        ROLLING_BACK.store(false, Ordering::SeqCst);
        return;
    };
    write_change(
        &dir,
        &Change {
            estado: "vuelta".into(),
            ..change
        },
    );
    core_process::stop(app).await;
    if let Err(e) = manager.apply_updates_and_restart(&info) {
        eprintln!("[nyx] no he podido volver: {e}");
        core_process::resume(app);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_feed_velopack_reads() {
        let path = Path::new("TepnyxNyx-anterior-full.nupkg");
        let text = feed("0.9.0", path, b"abc");
        let v: serde_json::Value = serde_json::from_str(&text).unwrap();
        let a = &v["Assets"][0];
        assert_eq!(a["Version"], "0.9.0");
        assert_eq!(a["Type"], "Full");
        assert_eq!(a["Size"], 3);
        assert_eq!(
            a["SHA256"],
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
        );
        // Velopack lo entiende como su propio índice.
        let parsed: velopack::VelopackAssetFeed = serde_json::from_str(&text).unwrap();
        assert_eq!(parsed.Assets[0].FileName, "TepnyxNyx-anterior-full.nupkg");
    }

    #[test]
    fn change_roundtrip() {
        let dir = std::env::temp_dir().join("nyx-vuelta");
        let _ = std::fs::create_dir_all(&dir);
        let c = Change {
            de: "0.9.0".into(),
            a: "0.9.1".into(),
            estado: "pendiente".into(),
        };
        write_change(&dir, &c);
        assert_eq!(read_change(&dir), Some(c));
    }
}
