//! En qué monitor aparece Nyx (SPEC sección 11, «Elección del monitor»).
//!
//! - «Sigue al ratón» (predeterminado) o «siempre en un monitor» (Ajustes → Apariencia).
//! - En partida con «solo voz», si Nyx tuviera que salir en el monitor del juego, sale en otro:
//!   el elegido en Ajustes → Modo partida, el principal o el primero sin el juego. Si no hay
//!   otro (un solo monitor), no sale en ninguno.
//!
//! La ventana de la isla manda la política (`overlay_policy`) cada vez que cambian los ajustes
//! o la partida; island.rs la aplica a todas las ventanas flotantes a la vez.

use serde::{Deserialize, Serialize};

use crate::win32::{self, Monitor};

#[derive(Clone, Copy, Debug, Default, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "lowercase")]
pub enum Follow {
    #[default]
    Cursor,
    Fixed,
}

/// Partida en marcha, tal como la cuenta el núcleo (protocolo v11).
#[derive(Clone, Debug, Default, Deserialize, PartialEq, Eq)]
pub struct Game {
    /// «Nyx en partida»: off | voice | normal.
    pub mode: String,
    /// Monitor del juego («\\.\DISPLAY1»); vacío si no se sabe.
    pub monitor: String,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "camelCase", default)]
pub struct Policy {
    pub follow: Follow,
    /// Monitor fijo; None o desconectado = el principal.
    pub fixed: Option<String>,
    /// Animación al cambiar de monitor estando visible.
    pub transition: bool,
    /// Monitor en partida («solo voz»); None = automático.
    pub alt: Option<String>,
    pub game: Option<Game>,
}

impl Default for Policy {
    fn default() -> Self {
        Policy {
            follow: Follow::Cursor,
            fixed: None,
            transition: true,
            alt: None,
            game: None,
        }
    }
}

/// Índice del monitor donde va Nyx, o None si no debe aparecer en ninguno.
pub fn choose(policy: &Policy, monitors: &[Monitor], cursor: Option<&str>) -> Option<usize> {
    if monitors.is_empty() {
        return None;
    }
    let find = |device: &str| monitors.iter().position(|m| m.device == device);
    let primary = monitors.iter().position(|m| m.primary).unwrap_or(0);
    let base = match policy.follow {
        Follow::Cursor => cursor.and_then(find).unwrap_or(primary),
        Follow::Fixed => policy.fixed.as_deref().and_then(find).unwrap_or(primary),
    };
    let Some(game) = &policy.game else {
        return Some(base);
    };
    if game.mode != "voice" {
        // «normal»: como siempre. («off» lo oculta la propia interfaz.)
        return Some(base);
    }
    if game.monitor.is_empty() {
        return None; // no se sabe dónde está el juego: mejor no aparecer encima
    }
    if monitors[base].device != game.monitor {
        return Some(base);
    }
    let free = |i: &usize| monitors[*i].device != game.monitor;
    policy
        .alt
        .as_deref()
        .and_then(find)
        .filter(free)
        .or_else(|| Some(primary).filter(free))
        .or_else(|| (0..monitors.len()).find(free))
}

/// Para Ajustes: los monitores con un nombre que se entiende.
#[derive(Clone, Debug, Serialize)]
pub struct MonitorInfo {
    pub device: String,
    pub label: String,
    pub primary: bool,
}

/// «Monitor 1 (principal) · 2560 × 1440», numerados de izquierda a derecha.
pub fn describe(monitors: &[Monitor]) -> Vec<MonitorInfo> {
    monitors
        .iter()
        .enumerate()
        .map(|(i, m)| MonitorInfo {
            device: m.device.clone(),
            label: format!(
                "Monitor {}{} · {} × {}",
                i + 1,
                if m.primary { " (principal)" } else { "" },
                m.area.width,
                m.area.height
            ),
            primary: m.primary,
        })
        .collect()
}

/// Ajustes → Apariencia y Modo partida: lista de monitores (vacía o de uno = bloqueado).
#[tauri::command]
pub fn monitors_list() -> Vec<MonitorInfo> {
    describe(&win32::monitors())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::win32::MonitorArea;

    fn monitor(device: &str, left: i32, primary: bool) -> Monitor {
        Monitor {
            device: device.to_string(),
            area: MonitorArea {
                left,
                top: 0,
                width: 1920,
                height: 1080,
                scale: 1.0,
            },
            primary,
        }
    }

    fn two() -> Vec<Monitor> {
        vec![monitor("A", 0, true), monitor("B", 1920, false)]
    }

    fn game(mode: &str, monitor: &str) -> Option<Game> {
        Some(Game {
            mode: mode.into(),
            monitor: monitor.into(),
        })
    }

    #[test]
    fn sigue_al_raton() {
        let p = Policy::default();
        assert_eq!(choose(&p, &two(), Some("B")), Some(1));
        assert_eq!(choose(&p, &two(), None), Some(0)); // sin ratón: el principal
    }

    #[test]
    fn monitor_fijo_y_si_se_desconecta_el_principal() {
        let mut p = Policy {
            follow: Follow::Fixed,
            fixed: Some("B".into()),
            ..Policy::default()
        };
        assert_eq!(choose(&p, &two(), Some("A")), Some(1));
        p.fixed = Some("C".into());
        assert_eq!(choose(&p, &two(), Some("B")), Some(0));
    }

    #[test]
    fn en_partida_solo_voz_va_a_otro_monitor() {
        let p = Policy {
            game: game("voice", "A"),
            ..Policy::default()
        };
        assert_eq!(choose(&p, &two(), Some("A")), Some(1));
        assert_eq!(choose(&p, &two(), Some("B")), Some(1)); // ya está en otro
    }

    #[test]
    fn el_monitor_elegido_para_partida_manda_si_no_tiene_el_juego() {
        let three = vec![
            monitor("A", 0, true),
            monitor("B", 1920, false),
            monitor("C", 3840, false),
        ];
        let p = Policy {
            alt: Some("C".into()),
            game: game("voice", "A"),
            ..Policy::default()
        };
        assert_eq!(choose(&p, &three, Some("A")), Some(2));
        // Si el elegido es justo el del juego, se busca otro.
        let p = Policy {
            alt: Some("A".into()),
            game: game("voice", "A"),
            ..Policy::default()
        };
        assert_eq!(choose(&p, &three, Some("A")), Some(1));
    }

    #[test]
    fn con_un_solo_monitor_en_partida_no_aparece() {
        let one = vec![monitor("A", 0, true)];
        let p = Policy {
            game: game("voice", "A"),
            ..Policy::default()
        };
        assert_eq!(choose(&p, &one, Some("A")), None);
        // Sin saber dónde está el juego, tampoco.
        let p = Policy {
            game: game("voice", ""),
            ..Policy::default()
        };
        assert_eq!(choose(&p, &two(), Some("B")), None);
    }

    #[test]
    fn en_modo_normal_aparece_como_siempre() {
        let p = Policy {
            game: game("normal", "A"),
            ..Policy::default()
        };
        assert_eq!(choose(&p, &two(), Some("A")), Some(0));
    }

    #[test]
    fn nombres_para_ajustes() {
        let names = describe(&two());
        assert_eq!(names[0].label, "Monitor 1 (principal) · 1920 × 1080");
        assert_eq!(names[1].label, "Monitor 2 · 1920 × 1080");
    }
}
