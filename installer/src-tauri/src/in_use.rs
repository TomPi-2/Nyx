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

/// Cierra Ollama y Everything si están abiertos y devuelve lo que hay que volver a abrir:
/// solo Everything (con `-startup`, sin ventana). Ollama no se vuelve a abrir: Nyx arranca su
/// servidor, oculto, cuando lo necesita. Sin PowerShell ni consolas: llamadas de Windows.
pub fn stop_helpers() -> Vec<(PathBuf, bool)> {
    let mut stopped: Vec<(PathBuf, bool)> = Vec::new();
    for (path, relaunch) in close_processes(&["ollama app.exe", "ollama.exe", "everything.exe"]) {
        let everything = path
            .file_name()
            .is_some_and(|n| n.to_string_lossy().eq_ignore_ascii_case("everything.exe"));
        if relaunch && everything && !stopped.iter().any(|(p, _)| p == &path) {
            stopped.push((path, true));
        }
    }
    stopped
}

/// Cierra los procesos con esos nombres (de este usuario: los demás no se dejan abrir) y
/// devuelve sus rutas. `true`: se ha podido cerrar.
#[cfg(windows)]
fn close_processes(names: &[&str]) -> Vec<(PathBuf, bool)> {
    use windows::Win32::Foundation::CloseHandle;
    use windows::Win32::System::Diagnostics::ToolHelp::{
        CreateToolhelp32Snapshot, PROCESSENTRY32W, Process32FirstW, Process32NextW,
        TH32CS_SNAPPROCESS,
    };
    use windows::Win32::System::Threading::{
        OpenProcess, PROCESS_NAME_WIN32, PROCESS_QUERY_LIMITED_INFORMATION, PROCESS_TERMINATE,
        QueryFullProcessImageNameW, TerminateProcess,
    };
    use windows::core::PWSTR;

    let mut out = Vec::new();
    // SAFETY: instantánea de procesos de solo lectura; cada handle se cierra.
    unsafe {
        let Ok(snapshot) = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0) else {
            return out;
        };
        let mut entry = PROCESSENTRY32W {
            dwSize: std::mem::size_of::<PROCESSENTRY32W>() as u32,
            ..Default::default()
        };
        let mut more = Process32FirstW(snapshot, &mut entry).is_ok();
        while more {
            let len = entry.szExeFile.iter().position(|&c| c == 0).unwrap_or(0);
            let name = String::from_utf16_lossy(&entry.szExeFile[..len]);
            if names.iter().any(|n| n.eq_ignore_ascii_case(&name))
                && let Ok(handle) = OpenProcess(
                    PROCESS_QUERY_LIMITED_INFORMATION | PROCESS_TERMINATE,
                    false,
                    entry.th32ProcessID,
                )
            {
                let mut buf = [0u16; 1024];
                let mut size = buf.len() as u32;
                let path = QueryFullProcessImageNameW(
                    handle,
                    PROCESS_NAME_WIN32,
                    PWSTR(buf.as_mut_ptr()),
                    &mut size,
                )
                .ok()
                .map(|()| PathBuf::from(String::from_utf16_lossy(&buf[..size as usize])));
                let closed = TerminateProcess(handle, 1).is_ok();
                let _ = CloseHandle(handle);
                if let Some(path) = path {
                    out.push((path, closed));
                }
            }
            more = Process32NextW(snapshot, &mut entry).is_ok();
        }
        let _ = CloseHandle(snapshot);
    }
    out
}

#[cfg(not(windows))]
fn close_processes(_names: &[&str]) -> Vec<(PathBuf, bool)> {
    Vec::new()
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
