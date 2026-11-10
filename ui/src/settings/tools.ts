/**
 * Nombres para mostrar de las herramientas (Ajustes → Modo partida). El núcleo manda el
 * nombre interno, el riesgo y la política por defecto; si aparece una herramienta nueva sin
 * nombre aquí, se muestra su nombre interno.
 */

export const TOOL_LABELS: Record<string, string> = {
  open_app: "Abrir aplicaciones y juegos",
  focus_window: "Cambiar a una ventana",
  window_layout: "Colocar ventanas",
  open_url: "Abrir páginas web",
  open_settings: "Abrir la Configuración de Windows",
  open_path: "Abrir carpetas y archivos",
  set_volume: "Cambiar el volumen",
  media_control: "Música y vídeo (pausa, siguiente…)",
  screenshot: "Captura de pantalla",
  close_app: "Cerrar aplicaciones",
  create_folder: "Crear carpetas",
  list_files: "Ver qué hay en una carpeta",
  find_files: "Buscar archivos",
  move_files: "Mover archivos",
  copy_files: "Copiar archivos",
  rename_file: "Renombrar archivos",
  set_alarm: "Alarmas y recordatorios",
  set_timer: "Temporizadores",
  send_hotkey: "Atajos de teclado",
  app_action: "Acciones dentro de una app",
  delete_files: "Mandar a la papelera",
  undo: "Deshacer",
};

export function toolLabel(name: string): string {
  return TOOL_LABELS[name] ?? name;
}
