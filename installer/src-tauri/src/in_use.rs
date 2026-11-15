//! Cuando la carpeta de Nyx está en uso y Velopack no puede sustituirla (I-110 → I-113).
//!
//! Al reinstalar o instalar otra versión, Velopack aparta la carpeta de la que hay
//! (`%LOCALAPPDATA%\TepnyxNyx`) y pone la nueva. Cierra él los programas que están dentro, pero
//! no los de fuera que la tienen como carpeta de trabajo: Ollama y Everything, si los abrió una
//! versión anterior de Nyx (las de ahora los abren en su propia carpeta). Entonces Windows dice
//! «Acceso denegado». Aquí se reconoce ese caso en el registro de Velopack, se cierran esos dos, se
//! reintenta y se vuelven a abrir como estaban.

use std::path::{Path, PathBuf};
use std::process::Command;

/// Lo que escribe Velopack cuando no puede apartar la carpeta de la versión instalada.
const IN_USE: &str = "Failed to remove existing application directory";
/// Programas que Nyx abre y siguen abiertos al cerrarla (proceso, ¿se abre con `-startup`?).
const HELPERS: [(&str, bool); 2] = [("ollama app", false), ("Everything", true)];

#[cfg(windows)]
const NO_WINDOW: u32 = 0x0800_0000; // CREATE_NO_WINDOW

fn log_path() -> Option<PathBuf> {
    let base = std::env::var_os("LOCALAPPDATA")?;
    Some(PathBuf::from(base).join("Velopack").join("velopack.log"))
}

/// Hasta dónde llega el registro de Velopack ahora (para leer solo lo de este intento).
pub fn log_len() -> u64 {
    log_path()
        .and_then(|p| std::fs::metadata(p).ok())
        .map(|m| m.len())
        .unwrap_or(0)
}

/// ¿El último intento falló por la carpeta en uso?
pub fn folder_in_use(since: u64) -> bool {
    let Some(path) = log_path() else {
        return false;
    };
    let Ok(bytes) = std::fs::read(path) else {
        return false;
    };
    let start = usize::try_from(since).unwrap_or(0).min(bytes.len());
    is_in_use(&String::from_utf8_lossy(&bytes[start..]))
}

fn is_in_use(log: &str) -> bool {
    log.contains(IN_USE)
}

fn hidden(program: &str) -> Command {
    let mut cmd = Command::new(program);
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        cmd.creation_flags(NO_WINDOW);
    }
    cmd
}

/// Cierra Ollama y Everything si están abiertos y devuelve lo que hay que volver a abrir.
pub fn stop_helpers() -> Vec<(PathBuf, bool)> {
    let mut stopped = Vec::new();
    for (name, startup) in HELPERS {
        let script = format!(
            "Get-Process -Name '{name}' -ErrorAction SilentlyContinue | ForEach-Object {{ $_.Path }}"
        );
        let Ok(out) = hidden("powershell")
            .args(["-NoProfile", "-NonInteractive", "-Command", &script])
            .output()
        else {
            continue;
        };
        let paths: Vec<PathBuf> = String::from_utf8_lossy(&out.stdout)
            .lines()
            .map(str::trim)
            .filter(|l| !l.is_empty())
            .map(PathBuf::from)
            .collect();
        if paths.is_empty() {
            continue;
        }
        let image = format!("{name}.exe");
        let _ = hidden("taskkill").args(["/F", "/T", "/IM", &image]).status();
        if name == "ollama app" {
            // El servidor que abrió su app, por si sigue vivo.
            let _ = hidden("taskkill").args(["/F", "/IM", "ollama.exe"]).status();
        }
        if let Some(first) = paths.into_iter().next() {
            stopped.push((first, startup));
        }
    }
    stopped
}

/// Los vuelve a abrir, cada uno en su carpeta (nunca en la de Nyx).
pub fn relaunch(stopped: &[(PathBuf, bool)]) {
    for (exe, startup) in stopped {
        let mut cmd = hidden(&exe.to_string_lossy());
        if *startup {
            cmd.arg("-startup");
        }
        if let Some(dir) = exe.parent().filter(|d| d.is_dir()) {
            cmd.current_dir(dir);
        }
        let _ = cmd.spawn();
    }
}

/// Para el detalle del error: qué se ha cerrado.
pub fn names(stopped: &[(PathBuf, bool)]) -> String {
    stopped
        .iter()
        .filter_map(|(p, _)| Path::new(p).file_stem().map(|s| s.to_string_lossy().into_owned()))
        .collect::<Vec<_>>()
        .join(", ")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn recognises_the_folder_in_use() {
        let log = "[setup:7220] [ERROR] An error has occurred: Failed to remove existing \
                   application directory, please close the application";
        assert!(is_in_use(log));
        assert!(!is_in_use("[setup] [ERROR] Not enough disk space"));
    }

    #[test]
    fn names_of_what_was_closed() {
        let stopped = vec![
            (PathBuf::from(r"C:\Programas\Ollama\ollama app.exe"), false),
            (PathBuf::from(r"C:\Program Files\Everything\Everything.exe"), true),
        ];
        assert_eq!(names(&stopped), "ollama app, Everything");
    }
}
