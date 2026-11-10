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
        // Alarmas y avisos: además de la burbuja, notificación de Windows (SPEC sección 11).
        .plugin(tauri_plugin_notification::init())
        .invoke_handler(tauri::generate_handler![
            core_process::core_endpoint,
            island::island_set_visible,
            island::island_set_hit_rects,
            island::island_set_size,
            island::island_backdrop_luma,
            input::input_hide,
            glass::glass_attach,
            glass::glass_set_options,
            glass::glass_set_shapes,
            glass::glass_poke,
            glass::glass_detach,
            glass::glass_set_game,
            glass::gallery::glass_toggle_bubble,
            glass::gallery::glass_close_gallery,
        ])
        .setup(|app| {
            let handle = app.handle();
            // Antes que las ventanas: el motor de cristal (no toca la GPU hasta que se usa).
            glass::init(handle);
            core_process::start(handle);
            island::create(handle)?;
            input::create(handle)?;
            hotkeys::register(handle);
            tray::build(handle)?;
            // Ayuda de desarrollo: NYX_GLASS=1 abre la galería del motor de cristal al arrancar.
            if std::env::var("NYX_GLASS").as_deref() == Ok("1") {
                glass::gallery::toggle(handle);
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
