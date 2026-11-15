//! Captura del micrófono sin filtros (WASAPI compartido, con `cpal`) y análisis de cada toma.
//!
//! - Se graba a la frecuencia del micrófono (normalmente 48 kHz), en mono (media de los
//!   canales) y sin procesar: nada de supresión de ruido ni control de volumen, que es lo que
//!   necesita el entrenamiento de una voz. Discord puede seguir usando el mismo micrófono.
//! - Mientras graba, cada bloque da el nivel (para la barra) y si se está hablando: así la
//!   toma se para sola tras un silencio.
//! - Al parar, se mira la toma: si ha saturado, si está baja, si hay ruido de fondo o si se ha
//!   cortado al principio o al final. La interfaz lo dice en palabras sencillas.

use std::sync::atomic::{AtomicBool, AtomicU32, Ordering};
use std::sync::mpsc::{Receiver, Sender, channel};
use std::sync::{Arc, Mutex};
use std::thread::JoinHandle;

use cpal::traits::{DeviceTrait, HostTrait, StreamTrait};
use serde::Serialize;

/// Lo que comparten el hilo del micrófono y las órdenes.
#[derive(Default)]
pub struct Shared {
    samples: Mutex<Vec<f32>>,
    /// Nivel del último bloque (0–1, RMS), como bits de f32.
    level: AtomicU32,
    rate: AtomicU32,
    speech: AtomicBool,
    /// Silencio seguido desde la última vez que se habló (ms).
    silence_ms: AtomicU32,
    /// Ruido de fondo estimado (RMS), como bits de f32.
    noise: AtomicU32,
    error: Mutex<Option<String>>,
}

impl Shared {
    fn f(bits: &AtomicU32) -> f32 {
        f32::from_bits(bits.load(Ordering::Relaxed))
    }
}

pub struct Capture {
    stop: Sender<()>,
    thread: Option<JoinHandle<()>>,
    pub shared: Arc<Shared>,
}

#[derive(Serialize)]
pub struct Status {
    pub level: f32,
    pub seconds: f32,
    pub speech: bool,
    pub silence_ms: u32,
    pub error: Option<String>,
}

/// Micrófonos de Windows y el predeterminado.
pub fn mics() -> (Vec<String>, Option<String>) {
    let host = cpal::default_host();
    let default = host.default_input_device().and_then(|d| d.name().ok());
    let names = host
        .input_devices()
        .map(|it| it.filter_map(|d| d.name().ok()).collect())
        .unwrap_or_default();
    (names, default)
}

fn find_device(name: Option<&str>) -> Result<cpal::Device, String> {
    let host = cpal::default_host();
    if let Some(name) = name
        && let Ok(mut devices) = host.input_devices()
        && let Some(d) = devices.find(|d| d.name().is_ok_and(|n| n == name))
    {
        return Ok(d);
    }
    host.default_input_device()
        .ok_or_else(|| "No encuentro ningún micrófono".to_string())
}

impl Capture {
    /// Empieza a grabar del micrófono `name` (o del predeterminado de Windows).
    pub fn start(name: Option<String>) -> Result<Capture, String> {
        let shared = Arc::new(Shared::default());
        let (stop, stop_rx) = channel::<()>();
        let (ready_tx, ready_rx) = channel::<Result<(), String>>();
        let worker = shared.clone();
        // El stream de cpal no se puede mover entre hilos: vive entero en el suyo.
        let thread = std::thread::spawn(move || {
            run(name, worker, stop_rx, ready_tx);
        });
        ready_rx
            .recv()
            .map_err(|_| "El micrófono no ha respondido".to_string())??;
        Ok(Capture {
            stop,
            thread: Some(thread),
            shared,
        })
    }

    pub fn status(&self) -> Status {
        let s = &self.shared;
        let rate = s.rate.load(Ordering::Relaxed).max(1);
        let len = s.samples.lock().map(|v| v.len()).unwrap_or(0);
        Status {
            level: Shared::f(&s.level),
            seconds: len as f32 / rate as f32,
            speech: s.speech.load(Ordering::Relaxed),
            silence_ms: s.silence_ms.load(Ordering::Relaxed),
            error: s.error.lock().ok().and_then(|e| e.clone()),
        }
    }

    /// Para y devuelve lo grabado (mono, -1..1) y la frecuencia.
    pub fn finish(mut self) -> (Vec<f32>, u32) {
        let _ = self.stop.send(());
        if let Some(t) = self.thread.take() {
            let _ = t.join();
        }
        let rate = self.shared.rate.load(Ordering::Relaxed);
        let samples = std::mem::take(
            &mut *self
                .shared
                .samples
                .lock()
                .unwrap_or_else(|e| e.into_inner()),
        );
        (samples, rate)
    }
}

fn run(
    name: Option<String>,
    shared: Arc<Shared>,
    stop: Receiver<()>,
    ready: Sender<Result<(), String>>,
) {
    let stream = match open(name.as_deref(), shared.clone()) {
        Ok(s) => s,
        Err(e) => {
            let _ = ready.send(Err(e));
            return;
        }
    };
    if let Err(e) = stream.play() {
        let _ = ready.send(Err(format!("No puedo abrir el micrófono: {e}")));
        return;
    }
    let _ = ready.send(Ok(()));
    let _ = stop.recv();
    drop(stream);
}

fn open(name: Option<&str>, shared: Arc<Shared>) -> Result<cpal::Stream, String> {
    let device = find_device(name)?;
    let config = device
        .default_input_config()
        .map_err(|e| format!("No puedo usar ese micrófono: {e}"))?;
    let channels = usize::from(config.channels()).max(1);
    shared.rate.store(config.sample_rate().0, Ordering::Relaxed);
    let err_shared = shared.clone();
    let on_error = move |e: cpal::StreamError| {
        if let Ok(mut slot) = err_shared.error.lock() {
            *slot = Some(format!("El micrófono ha fallado: {e}"));
        }
    };
    let format = config.sample_format();
    let config: cpal::StreamConfig = config.into();
    macro_rules! input {
        ($t:ty, $to:expr) => {{
            let shared = shared.clone();
            device.build_input_stream(
                &config,
                move |data: &[$t], _: &cpal::InputCallbackInfo| {
                    let mono: Vec<f32> = data
                        .chunks(channels)
                        .map(|frame| frame.iter().map(|&x| $to(x)).sum::<f32>() / channels as f32)
                        .collect();
                    push(&shared, &mono);
                },
                on_error,
                None,
            )
        }};
    }
    let stream = match format {
        cpal::SampleFormat::F32 => input!(f32, |x: f32| x),
        cpal::SampleFormat::I16 => input!(i16, |x: i16| f32::from(x) / 32768.0),
        cpal::SampleFormat::I32 => input!(i32, |x: i32| x as f32 / 2_147_483_648.0),
        cpal::SampleFormat::U16 => input!(u16, |x: u16| (f32::from(x) - 32768.0) / 32768.0),
        other => return Err(format!("Formato del micrófono no admitido: {other}")),
    };
    stream.map_err(|e| format!("No puedo abrir el micrófono: {e}"))
}

/// Un bloque nuevo: se guarda y se actualizan el nivel, el ruido de fondo y si se habla.
fn push(shared: &Shared, block: &[f32]) {
    if block.is_empty() {
        return;
    }
    let rate = shared.rate.load(Ordering::Relaxed).max(1);
    let rms = (block.iter().map(|x| x * x).sum::<f32>() / block.len() as f32).sqrt();
    shared.level.store(rms.to_bits(), Ordering::Relaxed);
    // Ruido de fondo: baja enseguida a lo más bajo y sube muy despacio.
    let mut noise = Shared::f(&shared.noise);
    noise = if noise == 0.0 || rms < noise {
        rms.max(1e-5)
    } else {
        noise * 1.002
    };
    shared.noise.store(noise.to_bits(), Ordering::Relaxed);
    let speaking = rms > (noise * 4.0).max(0.008); // y nunca por debajo de -42 dBFS
    let ms = (block.len() as u64 * 1000 / u64::from(rate)) as u32;
    if speaking {
        shared.speech.store(true, Ordering::Relaxed);
        shared.silence_ms.store(0, Ordering::Relaxed);
    } else {
        shared.silence_ms.fetch_add(ms, Ordering::Relaxed);
    }
    if let Ok(mut all) = shared.samples.lock() {
        all.extend_from_slice(block);
    }
}

/// Lo que se le dice de una toma (la interfaz lo pone en palabras).
#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct Analysis {
    pub seconds: f32,
    pub peak_db: f32,
    pub speech_db: f32,
    pub noise_db: f32,
    pub lead_s: f32,
    pub tail_s: f32,
    pub clipped: bool,
    pub quiet: bool,
    pub noisy: bool,
    pub cut_start: bool,
    pub cut_end: bool,
    pub empty: bool,
}

fn db(x: f32) -> f32 {
    20.0 * x.max(1e-6).log10()
}

/// Mira la toma por bloques de 20 ms.
pub fn analyze(samples: &[f32], rate: u32) -> Analysis {
    let rate = rate.max(1) as usize;
    let block = (rate / 50).max(1);
    let rms: Vec<f32> = samples
        .chunks(block)
        .map(|c| (c.iter().map(|x| x * x).sum::<f32>() / c.len() as f32).sqrt())
        .collect();
    let peak = samples.iter().fold(0.0f32, |m, x| m.max(x.abs()));
    let mut sorted = rms.clone();
    sorted.sort_by(f32::total_cmp);
    let noise = sorted.get(sorted.len() / 10).copied().unwrap_or(0.0);
    let threshold = (noise * 3.5).max(0.006);
    let first = rms.iter().position(|&r| r > threshold);
    let last = rms.iter().rposition(|&r| r > threshold);
    let block_s = block as f32 / rate as f32;
    let seconds = samples.len() as f32 / rate as f32;
    let (lead_s, tail_s, speech) = match (first, last) {
        (Some(a), Some(b)) => {
            let voiced: Vec<f32> = rms[a..=b]
                .iter()
                .copied()
                .filter(|&r| r > threshold)
                .collect();
            let level =
                (voiced.iter().map(|r| r * r).sum::<f32>() / voiced.len().max(1) as f32).sqrt();
            (
                a as f32 * block_s,
                seconds - (b + 1) as f32 * block_s,
                level,
            )
        }
        _ => (seconds, 0.0, 0.0),
    };
    let speech_s = seconds - lead_s - tail_s;
    let empty = first.is_none() || speech_s < 0.3;
    Analysis {
        seconds,
        peak_db: db(peak),
        speech_db: db(speech),
        noise_db: db(noise),
        lead_s,
        tail_s,
        clipped: peak >= 0.985,
        quiet: !empty && db(speech) < -32.0 && db(peak) < -14.0,
        noisy: db(noise) > -50.0,
        cut_start: !empty && lead_s < 0.12,
        cut_end: !empty && tail_s < 0.12,
        empty,
    }
}

/// WAV mono de 24 bits a la frecuencia del micrófono.
pub fn write_wav(path: &std::path::Path, samples: &[f32], rate: u32) -> Result<(), String> {
    let spec = hound::WavSpec {
        channels: 1,
        sample_rate: rate,
        bits_per_sample: 24,
        sample_format: hound::SampleFormat::Int,
    };
    let mut w = hound::WavWriter::create(path, spec).map_err(|e| e.to_string())?;
    for &x in samples {
        let v = (x.clamp(-1.0, 1.0) * 8_388_607.0).round() as i32;
        w.write_sample(v).map_err(|e| e.to_string())?;
    }
    w.finalize().map_err(|e| e.to_string())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn tone(seconds: f32, amp: f32, rate: u32) -> Vec<f32> {
        (0..(seconds * rate as f32) as usize)
            .map(|i| amp * (i as f32 * 0.05).sin())
            .collect()
    }

    #[test]
    fn a_good_take() {
        let rate = 48_000;
        let mut s = vec![0.0005; rate as usize / 2];
        s.extend(tone(2.0, 0.3, rate));
        s.extend(vec![0.0005; rate as usize / 2]);
        let a = analyze(&s, rate);
        assert!(!a.empty && !a.clipped && !a.quiet && !a.noisy);
        assert!(!a.cut_start && !a.cut_end);
        assert!((a.lead_s - 0.5).abs() < 0.05);
    }

    #[test]
    fn cut_clipped_and_quiet() {
        let rate = 48_000;
        let mut s = tone(1.0, 1.0, rate);
        s.extend(vec![0.0; rate as usize / 2]);
        let a = analyze(&s, rate);
        assert!(a.clipped && a.cut_start && !a.cut_end);
        let quiet = analyze(
            &[vec![0.0; 24_000], tone(1.0, 0.01, rate), vec![0.0; 24_000]].concat(),
            rate,
        );
        assert!(quiet.quiet);
        assert!(analyze(&vec![0.0; 48_000], rate).empty);
    }

    #[test]
    fn wav_is_24_bit_mono() {
        let path = std::env::temp_dir().join("grabadora-prueba.wav");
        write_wav(&path, &tone(0.1, 0.5, 48_000), 48_000).unwrap();
        let r = hound::WavReader::open(&path).unwrap();
        assert_eq!(r.spec().bits_per_sample, 24);
        assert_eq!(r.spec().channels, 1);
        assert_eq!(r.len(), 4800);
    }
}
