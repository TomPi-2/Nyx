//! Abrir carpetas de Nyx en el Explorador (Ajustes → Ayuda: registros y acciones).

use std::path::PathBuf;

/// Solo las carpetas conocidas, dentro de `%LOCALAPPDATA%\Nyx`.
#[tauri::command]
pub fn open_folder(kind: String) -> Result<(), String> {
    let base = std::env::var_os("LOCALAPPDATA").ok_or("sin LOCALAPPDATA")?;
    let sub = match kind.as_str() {
        "logs" => "logs",
        "actions" => "actions",
        _ => return Err(format!("carpeta desconocida: {kind}")),
    };
    let path = PathBuf::from(base).join("Nyx").join(sub);
    std::fs::create_dir_all(&path).map_err(|e| e.to_string())?;
    std::process::Command::new("explorer")
        .arg(&path)
        .spawn()
        .map(|_| ())
        .map_err(|e| e.to_string())
}
