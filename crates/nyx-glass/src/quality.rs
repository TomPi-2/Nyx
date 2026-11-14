//! Niveles de calidad del cristal y bajadas automáticas (propuesta, apartado 2.5).
//!
//! Decisión del usuario (2026-11-10): en Ajustes se elige «Auto» o un nivel concreto.
//! - Auto: el motor baja solo con batería, ahorro de energía, transparencias de Windows
//!   desactivadas o una GPU que no llega.
//! - Nivel concreto: se respeta, salvo en partida, donde se pasa a Bajo **sin excepción**
//!   (nunca se captura la pantalla con un juego abierto, también por los antitrampas).
//!
//! El nivel «Compositor» (pincel de fondo de Windows, ruta A) se descartó: en el portátil
//! de pruebas el pincel no está disponible.

use serde::{Deserialize, Serialize};

/// Lo que elige el usuario.
#[derive(Clone, Copy, Debug, Default, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "lowercase")]
pub enum Preference {
    #[default]
    Auto,
    Alto,
    Medio,
    Bajo,
}

/// Lo que dibuja el motor, de menos a más coste: `Bajo < Medio < Alto`.
#[derive(Clone, Copy, Debug, Deserialize, Serialize, PartialEq, Eq, PartialOrd, Ord)]
#[serde(rename_all = "lowercase")]
pub enum Level {
    /// Tinte translúcido: no mira lo de detrás. Casi gratis.
    Bajo,
    /// Desenfoque en tiempo real + tinte + brillo sencillo.
    Medio,
    /// Medio + refracción en el borde + brillo especular.
    Alto,
}

impl Level {
    /// ¿Necesita capturar la pantalla?
    pub fn captures(self) -> bool {
        self >= Level::Medio
    }

    /// Un nivel menos (para cuando la GPU no llega).
    pub fn lower(self) -> Level {
        match self {
            Level::Alto => Level::Medio,
            Level::Medio | Level::Bajo => Level::Bajo,
        }
    }
}

/// Movimiento del borde líquido.
#[derive(Clone, Copy, Debug, Default, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "lowercase")]
pub enum Motion {
    /// Ondula sin parar.
    #[default]
    Siempre,
    /// Ondula al aparecer y al interactuar; luego se frena y se queda quieto.
    Interaccion,
    /// Borde fijo (sigue teniendo la forma líquida, pero no se mueve).
    Quieto,
}

/// Estado del sistema que puede bajar el nivel.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct SystemState {
    pub game: bool,
    pub transparency: bool,
    pub reduce_motion: bool,
    pub on_battery: bool,
    pub energy_saver: bool,
}

/// Lo que el motor no puede hacer en este equipo o en este momento.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct Limits {
    pub capture_failed: bool,
    /// Tope por rendimiento de la GPU (medido; solo en Auto).
    pub gpu_cap: Option<Level>,
}

/// Nivel que se usa de verdad y, si es menor que el pedido, por qué.
pub fn effective(
    preference: Preference,
    sys: &SystemState,
    limits: &Limits,
) -> (Level, Option<&'static str>) {
    let mut level = match preference {
        Preference::Auto | Preference::Alto => Level::Alto,
        Preference::Medio => Level::Medio,
        Preference::Bajo => Level::Bajo,
    };
    let mut reason = None;
    let mut cap = |max: Level, why: &'static str| {
        if level > max {
            level = max;
            reason = Some(why);
        }
    };
    // Sin excepción, también con un nivel concreto.
    if sys.game {
        cap(Level::Bajo, "partida en curso");
    }
    if preference == Preference::Auto {
        // Del más restrictivo al menos: el motivo que se muestra es el que más baja.
        if !sys.transparency {
            cap(Level::Bajo, "transparencias de Windows desactivadas");
        }
        if sys.energy_saver {
            cap(Level::Bajo, "ahorro de energía");
        }
        if let Some(max) = limits.gpu_cap {
            cap(max, "la GPU no llega");
        }
        if sys.on_battery {
            cap(Level::Medio, "con batería");
        }
    }
    // Si no se puede capturar, no se puede.
    if limits.capture_failed {
        cap(Level::Bajo, "captura no disponible");
    }
    (level, reason)
}

/// ¿Se mueve el borde? Las partidas y «reducir movimiento» de Windows lo paran.
pub fn motion_allowed(motion: Motion, sys: &SystemState) -> bool {
    motion != Motion::Quieto && !sys.reduce_motion && !sys.game
}

#[cfg(windows)]
pub fn read_system(game: bool) -> SystemState {
    use windows::Win32::System::Power::{GetSystemPowerStatus, SYSTEM_POWER_STATUS};
    use windows::Win32::System::Registry::{HKEY_CURRENT_USER, RRF_RT_REG_DWORD, RegGetValueW};
    use windows::Win32::UI::WindowsAndMessaging::{
        SPI_GETCLIENTAREAANIMATION, SYSTEM_PARAMETERS_INFO_UPDATE_FLAGS, SystemParametersInfoW,
    };
    use windows::core::{BOOL, w};

    // Configuración → Personalización → Colores → «Efectos de transparencia».
    let mut value: u32 = 1;
    let mut size = size_of::<u32>() as u32;
    // SAFETY: lectura de un DWORD del registro en variables locales del tamaño indicado.
    let transparency = unsafe {
        RegGetValueW(
            HKEY_CURRENT_USER,
            w!(r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"),
            w!("EnableTransparency"),
            RRF_RT_REG_DWORD,
            None,
            Some(&mut value as *mut u32 as *mut _),
            Some(&mut size),
        )
    }
    .is_err()
        || value != 0;

    // Accesibilidad → Efectos visuales → «Efectos de animación».
    let mut animations = BOOL(1);
    // SAFETY: SPI_GETCLIENTAREAANIMATION escribe un BOOL en la variable local.
    let _ = unsafe {
        SystemParametersInfoW(
            SPI_GETCLIENTAREAANIMATION,
            0,
            Some(&mut animations as *mut BOOL as *mut _),
            SYSTEM_PARAMETERS_INFO_UPDATE_FLAGS(0),
        )
    };

    let mut power = SYSTEM_POWER_STATUS::default();
    // SAFETY: rellena una estructura local.
    let power_ok = unsafe { GetSystemPowerStatus(&mut power) }.is_ok();

    SystemState {
        game,
        transparency,
        reduce_motion: !animations.as_bool(),
        // 0 = sin corriente; 1 = enchufado; 255 = desconocido (equipo de sobremesa).
        on_battery: power_ok && power.ACLineStatus == 0,
        energy_saver: power_ok && power.SystemStatusFlag == 1,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn sys() -> SystemState {
        SystemState {
            transparency: true,
            ..SystemState::default()
        }
    }

    #[test]
    fn auto_sin_restricciones_es_alto() {
        let (q, why) = effective(Preference::Auto, &sys(), &Limits::default());
        assert_eq!((q, why), (Level::Alto, None));
    }

    #[test]
    fn en_partida_se_pasa_a_bajo_sin_excepcion() {
        let s = SystemState {
            game: true,
            ..sys()
        };
        for pref in [Preference::Auto, Preference::Alto, Preference::Medio] {
            let (q, why) = effective(pref, &s, &Limits::default());
            assert_eq!(q, Level::Bajo);
            assert!(!q.captures());
            assert_eq!(why, Some("partida en curso"));
        }
    }

    #[test]
    fn un_nivel_concreto_ignora_bateria_y_gpu() {
        let s = SystemState {
            on_battery: true,
            energy_saver: true,
            transparency: false,
            ..sys()
        };
        let limits = Limits {
            gpu_cap: Some(Level::Bajo),
            ..Limits::default()
        };
        assert_eq!(effective(Preference::Alto, &s, &limits).0, Level::Alto);
        assert_eq!(effective(Preference::Medio, &s, &limits).0, Level::Medio);
    }

    #[test]
    fn auto_baja_con_bateria_y_mas_con_transparencias_desactivadas() {
        let s = SystemState {
            on_battery: true,
            ..sys()
        };
        assert_eq!(
            effective(Preference::Auto, &s, &Limits::default()),
            (Level::Medio, Some("con batería"))
        );
        let s = SystemState {
            transparency: false,
            ..s
        };
        assert_eq!(
            effective(Preference::Auto, &s, &Limits::default()),
            (Level::Bajo, Some("transparencias de Windows desactivadas"))
        );
    }

    #[test]
    fn sin_captura_se_usa_el_tinte() {
        let limits = Limits {
            capture_failed: true,
            ..Limits::default()
        };
        assert_eq!(
            effective(Preference::Alto, &sys(), &limits),
            (Level::Bajo, Some("captura no disponible"))
        );
    }

    #[test]
    fn el_movimiento_se_para_en_partida_y_con_reducir_movimiento() {
        assert!(motion_allowed(Motion::Siempre, &sys()));
        let s = SystemState {
            reduce_motion: true,
            ..sys()
        };
        assert!(!motion_allowed(Motion::Siempre, &s));
        let s = SystemState {
            game: true,
            ..sys()
        };
        assert!(!motion_allowed(Motion::Interaccion, &s));
        assert!(!motion_allowed(Motion::Quieto, &sys()));
    }

    #[test]
    fn bajar_un_nivel() {
        assert_eq!(Level::Alto.lower(), Level::Medio);
        assert_eq!(Level::Medio.lower(), Level::Bajo);
        assert_eq!(Level::Bajo.lower(), Level::Bajo);
    }
}
