// Prevents additional console window on Windows in release, DO NOT REMOVE!!
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    // Lo primero (Velopack, 9.06): atiende la instalación, las actualizaciones y la
    // desinstalación, y aplica una versión ya descargada si se cerró Nyx antes de aplicarla.
    // Sin instalar con Velopack (desarrollo) no hace nada.
    velopack::VelopackApp::build()
        .on_first_run(|_| {
            // Abierta por el Setup durante la instalación: la abre el instalador al acabar.
            if nyx_ui_lib::install_hooks::opened_by_installer() {
                std::process::exit(0);
            }
        })
        .on_before_uninstall_fast_callback(|_| nyx_ui_lib::install_hooks::cleanup_on_uninstall())
        .run();
    nyx_ui_lib::run()
}
