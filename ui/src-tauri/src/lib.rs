//! Proceso principal de Nyx: bandeja, instancia única, ventanas y núcleo Python.

mod core_process;
mod glass;
mod hotkeys;
mod input;
mod island;
mod tray;
mod win32;

use tauri::RunEvent;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let app = tauri::Builder::default()
        // Debe registrarse el primero (instancia única, SPEC sección 14).
        .plugin(tauri_plugin_single_instance::init(|_app, _argv, _cwd| {
            // Fase 5: abrir la ventana de Ajustes.
            eprintln!("[nyx] ya hay una instancia en marcha");
        }))
        .plugin(hotkeys::plugin())
        .invoke_handler(tauri::generate_handler![
            core_process::core_endpoint,
            island::island_set_visible,
            input::input_hide,
        ])
        .setup(|app| {
            let handle = app.handle();
            core_process::start(handle);
            island::create(handle)?;
            input::create(handle)?;
            hotkeys::register(handle);
            tray::build(handle)?;
            // Ayuda de desarrollo: NYX_GLASS_TEST=1 abre la prueba de cristal al arrancar.
            if std::env::var("NYX_GLASS_TEST").as_deref() == Ok("1") {
                glass::toggle(handle);
            }
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("no se pudo iniciar Nyx");

    app.run(|_app, event| {
        // Nyx vive en la bandeja: cerrar ventanas no lo termina; solo «Salir».
        if let RunEvent::ExitRequested {
            api, code: None, ..
        } = event
        {
            api.prevent_exit();
        }
    });
}
