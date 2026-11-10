//! Captura del monitor con Windows.Graphics.Capture (ruta B).
//!
//! - Sin borde amarillo ni cursor, y sin las ventanas de Nyx (WDA_EXCLUDEFROMCAPTURE).
//! - Solo mientras hay una lámina visible que la necesita; si no, se cierra (0 % de GPU).
//! - Windows solo entrega fotograma cuando cambia la pantalla, y como mucho a 30 Hz.
//! - Las imágenes se quedan en la memoria de la GPU: no se guardan, no se envían y no
//!   pasan al núcleo ni al LLM (propuesta, apartado 2.8).

use std::sync::Arc;
use std::sync::atomic::{AtomicBool, Ordering};

use windows::Foundation::{TimeSpan, TypedEventHandler};
use windows::Graphics::Capture::{
    Direct3D11CaptureFrame, Direct3D11CaptureFramePool, GraphicsCaptureItem, GraphicsCaptureSession,
};
use windows::Graphics::DirectX::Direct3D11::IDirect3DDevice;
use windows::Graphics::DirectX::DirectXPixelFormat;
use windows::Graphics::SizeInt32;
use windows::Win32::Graphics::Direct3D11::ID3D11Texture2D;
use windows::Win32::Graphics::Gdi::{GetMonitorInfoW, HMONITOR, MONITORINFO};
use windows::Win32::System::WinRT::Direct3D11::IDirect3DDxgiInterfaceAccess;
use windows::Win32::System::WinRT::Graphics::Capture::IGraphicsCaptureItemInterop;
use windows::core::{IInspectable, Interface, Result, factory};

use super::Wake;

/// 30 Hz como mucho (TimeSpan va en unidades de 100 ns).
const MIN_INTERVAL: TimeSpan = TimeSpan { Duration: 333_333 };

pub struct MonitorCapture {
    pub monitor: HMONITOR,
    /// Esquina del monitor en el escritorio virtual (píxeles físicos).
    pub origin: (i32, i32),
    pool: Direct3D11CaptureFramePool,
    session: GraphicsCaptureSession,
    size: SizeInt32,
    fresh: Arc<AtomicBool>,
    /// Último fotograma: se guarda para recortar otra vez si la ventana se mueve.
    frame: Option<(Direct3D11CaptureFrame, ID3D11Texture2D, (u32, u32))>,
    /// Fotogramas recibidos desde la última estadística.
    pub frames: u32,
    /// Última vez que una ventana visible la necesitó (engine.rs la cierra un rato después).
    pub needed_at: std::time::Instant,
}

impl MonitorCapture {
    pub fn start(monitor: HMONITOR, device: &IDirect3DDevice, wake: Arc<Wake>) -> Result<Self> {
        let interop = factory::<GraphicsCaptureItem, IGraphicsCaptureItemInterop>()?;
        // SAFETY: HMONITOR válido obtenido de MonitorFromWindow.
        let item: GraphicsCaptureItem = unsafe { interop.CreateForMonitor(monitor)? };
        let size = item.Size()?;
        let pool = Direct3D11CaptureFramePool::CreateFreeThreaded(
            device,
            DirectXPixelFormat::B8G8R8A8UIntNormalized,
            2,
            size,
        )?;
        let fresh = Arc::new(AtomicBool::new(false));
        let flag = fresh.clone();
        // Se llama en un hilo del sistema: solo avisa al hilo del motor.
        pool.FrameArrived(
            &TypedEventHandler::<Direct3D11CaptureFramePool, IInspectable>::new(move |_, _| {
                flag.store(true, Ordering::Release);
                wake.set();
                Ok(())
            }),
        )?;
        let session = pool.CreateCaptureSession(&item)?;
        // Estas tres opciones no existen en versiones antiguas de Windows 11: si fallan,
        // se sigue sin ellas (solo es más coste o un borde amarillo).
        let _ = session.SetIsBorderRequired(false);
        let _ = session.SetIsCursorCaptureEnabled(false);
        let _ = session.SetMinUpdateInterval(MIN_INTERVAL);
        session.StartCapture()?;

        let mut info = MONITORINFO {
            cbSize: size_of::<MONITORINFO>() as u32,
            ..Default::default()
        };
        // SAFETY: estructura local con su tamaño.
        let _ = unsafe { GetMonitorInfoW(monitor, &mut info) };
        Ok(MonitorCapture {
            monitor,
            origin: (info.rcMonitor.left, info.rcMonitor.top),
            pool,
            session,
            size,
            fresh,
            frame: None,
            frames: 0,
            needed_at: std::time::Instant::now(),
        })
    }

    /// Recoge el fotograma más reciente, si ha llegado uno. Devuelve si hay imagen nueva.
    pub fn poll(&mut self, device: &IDirect3DDevice) -> Result<bool> {
        if !self.fresh.swap(false, Ordering::AcqRel) {
            return Ok(false);
        }
        let mut latest = None;
        // Puede haber varios en cola: solo interesa el último.
        while let Ok(frame) = self.pool.TryGetNextFrame() {
            if let Some(old) = latest.replace(frame) {
                let _ = old.Close();
            }
        }
        let Some(frame) = latest else {
            return Ok(false);
        };
        // Cambio de resolución del monitor: se recrea el grupo con el tamaño nuevo.
        let size = frame.ContentSize()?;
        if size != self.size {
            self.size = size;
            self.pool
                .Recreate(device, DirectXPixelFormat::B8G8R8A8UIntNormalized, 2, size)?;
        }
        let access: IDirect3DDxgiInterfaceAccess = frame.Surface()?.cast()?;
        // SAFETY: la superficie de la captura es una textura D3D11 del mismo dispositivo.
        let texture: ID3D11Texture2D = unsafe { access.GetInterface()? };
        let dims = (size.Width.max(0) as u32, size.Height.max(0) as u32);
        if let Some((old, _, _)) = self.frame.replace((frame, texture, dims)) {
            let _ = old.Close();
        }
        self.frames += 1;
        Ok(true)
    }

    /// Textura del último fotograma y su tamaño.
    pub fn texture(&self) -> Option<(&ID3D11Texture2D, (u32, u32))> {
        self.frame.as_ref().map(|(_, t, dims)| (t, *dims))
    }
}

impl Drop for MonitorCapture {
    fn drop(&mut self) {
        if let Some((frame, _, _)) = self.frame.take() {
            let _ = frame.Close();
        }
        let _ = self.session.Close();
        let _ = self.pool.Close();
    }
}
