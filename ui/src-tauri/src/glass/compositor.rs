//! Composición de Windows (Windows.UI.Composition): pone la lámina detrás de la WebView.
//!
//! Cada ventana con cristal recibe un árbol de visuales propio (`DesktopWindowTarget` sin
//! «topmost»: queda por debajo de la WebView, que es una ventana hija). Así el texto y los
//! controles de Svelte siguen encima, sin tocar WebView2 y sin una segunda ventana que
//! haya que mantener pegada. El único visual muestra la cadena de intercambio de
//! renderer.rs (alfa por píxel: la silueta líquida sale suavizada, sin escalones).
//!
//! El pincel de fondo de Windows (`HostBackdropBrush`, ruta A) se probó y se descartó el
//! 2026-11-10: en el portátil de pruebas no está disponible.

use windows::UI::Composition::Desktop::DesktopWindowTarget;
use windows::UI::Composition::{CompositionStretch, Compositor, ContainerVisual, SpriteVisual};
use windows::Win32::Foundation::HWND;
use windows::Win32::Graphics::Dxgi::IDXGISwapChain1;
use windows::Win32::System::WinRT::Composition::{ICompositorDesktopInterop, ICompositorInterop};
use windows::core::{Interface, Result};
use windows_numerics::Vector2;

pub struct Layers {
    // Se guarda para que el árbol siga vivo mientras exista la ventana.
    _target: DesktopWindowTarget,
    root: ContainerVisual,
    main: SpriteVisual,
}

impl Layers {
    pub fn new(
        compositor: &Compositor,
        hwnd: HWND,
        swapchain: &IDXGISwapChain1,
        size: (u32, u32),
    ) -> Result<Layers> {
        let desktop: ICompositorDesktopInterop = compositor.cast()?;
        // SAFETY: hwnd es una ventana viva de este proceso.
        let target = unsafe { desktop.CreateDesktopWindowTarget(hwnd, false)? };
        let root = compositor.CreateContainerVisual()?;
        target.SetRoot(&root)?;

        let interop: ICompositorInterop = compositor.cast()?;
        // SAFETY: cadena de intercambio creada para composición.
        let surface = unsafe { interop.CreateCompositionSurfaceForSwapChain(swapchain)? };
        let surface = compositor.CreateSurfaceBrushWithSurface(&surface)?;
        surface.SetStretch(CompositionStretch::None)?;

        let main = compositor.CreateSpriteVisual()?;
        main.SetBrush(&surface)?;
        root.Children()?.InsertAtTop(&main)?;

        let layers = Layers {
            _target: target,
            root,
            main,
        };
        layers.set_size(size)?;
        Ok(layers)
    }

    pub fn set_size(&self, (width, height): (u32, u32)) -> Result<()> {
        self.main.SetSize(Vector2 {
            X: width as f32,
            Y: height as f32,
        })
    }
}

impl Drop for Layers {
    fn drop(&mut self) {
        let _ = self.root.Children().and_then(|c| c.RemoveAll());
    }
}
