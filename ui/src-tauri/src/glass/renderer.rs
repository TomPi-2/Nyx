//! Direct3D 11: dispositivo, shaders y las pasadas del cristal.
//!
//! Por cada ventana: una cadena de intercambio para composición (transparencia por píxel,
//! sin regiones ni escalones), la imagen de detrás a resolución completa y una cadena de
//! texturas cada vez más pequeñas para el desenfoque Kawase doble. El desenfoque solo se
//! repite cuando cambia lo de detrás; la lámina se redibuja cuando se mueve el borde.

use std::collections::VecDeque;

use windows::Graphics::DirectX::Direct3D11::IDirect3DDevice;
use windows::Win32::Foundation::{E_FAIL, HMODULE};
use windows::Win32::Graphics::Direct3D::Fxc::{D3DCOMPILE_OPTIMIZATION_LEVEL3, D3DCompile};
use windows::Win32::Graphics::Direct3D::{
    D3D_DRIVER_TYPE_HARDWARE, D3D_FEATURE_LEVEL_10_1, D3D_FEATURE_LEVEL_11_0,
    D3D_FEATURE_LEVEL_11_1, D3D11_PRIMITIVE_TOPOLOGY_TRIANGLELIST, ID3DBlob, ID3DInclude,
};
use windows::Win32::Graphics::Direct3D11::{
    D3D11_ASYNC_GETDATA_DONOTFLUSH, D3D11_BIND_CONSTANT_BUFFER, D3D11_BIND_RENDER_TARGET,
    D3D11_BIND_SHADER_RESOURCE, D3D11_BOX, D3D11_BUFFER_DESC, D3D11_COMPARISON_NEVER,
    D3D11_CREATE_DEVICE_BGRA_SUPPORT, D3D11_FILTER_MIN_MAG_MIP_LINEAR,
    D3D11_QUERY_DATA_TIMESTAMP_DISJOINT, D3D11_QUERY_DESC, D3D11_QUERY_TIMESTAMP,
    D3D11_QUERY_TIMESTAMP_DISJOINT, D3D11_SAMPLER_DESC, D3D11_SDK_VERSION,
    D3D11_TEXTURE_ADDRESS_CLAMP, D3D11_TEXTURE2D_DESC, D3D11_USAGE_DEFAULT, D3D11_VIEWPORT,
    D3D11CreateDevice, ID3D11Buffer, ID3D11Device, ID3D11DeviceContext, ID3D11PixelShader,
    ID3D11Query, ID3D11RenderTargetView, ID3D11SamplerState, ID3D11ShaderResourceView,
    ID3D11Texture2D, ID3D11VertexShader,
};
use windows::Win32::Graphics::Dxgi::Common::{
    DXGI_ALPHA_MODE_PREMULTIPLIED, DXGI_FORMAT_B8G8R8A8_UNORM, DXGI_SAMPLE_DESC,
};
use windows::Win32::Graphics::Dxgi::{
    DXGI_PRESENT, DXGI_SCALING_STRETCH, DXGI_SWAP_CHAIN_DESC1, DXGI_SWAP_CHAIN_FLAG,
    DXGI_SWAP_EFFECT_FLIP_SEQUENTIAL, DXGI_USAGE_RENDER_TARGET_OUTPUT, IDXGIDevice, IDXGIFactory2,
    IDXGISwapChain1,
};
use windows::Win32::System::WinRT::Direct3D11::CreateDirect3D11DeviceFromDXGIDevice;
use windows::core::{Error, Interface, PCSTR, Result, s};

const SHADERS: &str = include_str!("shaders/glass.hlsl");
pub const MAX_SHAPES: usize = 8;

/// Modo de la pasada final (igual que en glass.hlsl).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Mode {
    Tint = 0,
    Blur = 1,
    Glass = 2,
}

/// Constantes de la lámina. Mismo orden y tamaño que el `cbuffer Glass` del shader.
#[repr(C)]
#[derive(Clone, Copy, Debug, Default)]
pub struct GlassParams {
    pub size: [f32; 2],
    pub loop_phase: [f32; 2],
    pub amp: f32,
    pub wave: f32,
    pub mode: u32,
    pub count: u32,
    pub tint: [f32; 4],
    pub refraction: f32,
    pub band: f32,
    pub specular: f32,
    pub grain: f32,
    pub saturation: f32,
    pub shadow: f32,
    pub scale: f32,
    pub sheen: f32,
    pub seed: f32,
    pub pad: [f32; 3],
    pub rects: [[f32; 4]; MAX_SHAPES],
    pub params: [[f32; 4]; MAX_SHAPES],
}

#[repr(C)]
#[derive(Clone, Copy, Debug, Default)]
struct BlurParams {
    texel: [f32; 2],
    offset: f32,
    pad: f32,
}

/// Dispositivo y programas comunes a todas las ventanas.
pub struct Gpu {
    pub device: ID3D11Device,
    pub context: ID3D11DeviceContext,
    pub winrt_device: IDirect3DDevice,
    factory: IDXGIFactory2,
    pub adapter: String,
    vs: ID3D11VertexShader,
    ps_down: ID3D11PixelShader,
    ps_up: ID3D11PixelShader,
    ps_glass: ID3D11PixelShader,
    sampler: ID3D11SamplerState,
    cb_blur: ID3D11Buffer,
    cb_glass: ID3D11Buffer,
    timer: GpuTimer,
}

impl Gpu {
    pub fn new() -> Result<Gpu> {
        let mut device = None;
        let mut context = None;
        // SAFETY: llamada estándar; los punteros de salida son variables locales.
        unsafe {
            D3D11CreateDevice(
                None,
                D3D_DRIVER_TYPE_HARDWARE,
                HMODULE::default(),
                // BGRA: necesario para la composición de Windows.
                D3D11_CREATE_DEVICE_BGRA_SUPPORT,
                Some(&[
                    D3D_FEATURE_LEVEL_11_1,
                    D3D_FEATURE_LEVEL_11_0,
                    D3D_FEATURE_LEVEL_10_1,
                ]),
                D3D11_SDK_VERSION,
                Some(&mut device),
                None,
                Some(&mut context),
            )?;
        }
        let device: ID3D11Device = device.ok_or_else(|| fail("sin dispositivo D3D11"))?;
        let context = context.ok_or_else(|| fail("sin contexto D3D11"))?;

        let dxgi_device: IDXGIDevice = device.cast()?;
        // SAFETY: consultas sobre objetos DXGI válidos.
        let (adapter, factory) = unsafe {
            let adapter = dxgi_device.GetAdapter()?;
            let desc = adapter.GetDesc()?;
            let len = desc
                .Description
                .iter()
                .position(|&c| c == 0)
                .unwrap_or(desc.Description.len());
            let name = String::from_utf16_lossy(&desc.Description[..len]);
            (name, adapter.GetParent::<IDXGIFactory2>()?)
        };
        // El mismo dispositivo, visto desde WinRT, para la captura de pantalla.
        // SAFETY: interop documentado entre DXGI y Windows.Graphics.DirectX.
        let winrt_device: IDirect3DDevice =
            unsafe { CreateDirect3D11DeviceFromDXGIDevice(&dxgi_device)? }.cast()?;

        let vs_code = compile(s!("VSMain"), s!("vs_5_0"))?;
        let mut vs = None;
        let mut ps_down = None;
        let mut ps_up = None;
        let mut ps_glass = None;
        // SAFETY: código compilado arriba; punteros de salida locales.
        unsafe {
            device.CreateVertexShader(&vs_code, None, Some(&mut vs))?;
            device.CreatePixelShader(
                &compile(s!("PSDown"), s!("ps_5_0"))?,
                None,
                Some(&mut ps_down),
            )?;
            device.CreatePixelShader(
                &compile(s!("PSUp"), s!("ps_5_0"))?,
                None,
                Some(&mut ps_up),
            )?;
            device.CreatePixelShader(
                &compile(s!("PSGlass"), s!("ps_5_0"))?,
                None,
                Some(&mut ps_glass),
            )?;
        }

        let sampler_desc = D3D11_SAMPLER_DESC {
            Filter: D3D11_FILTER_MIN_MAG_MIP_LINEAR,
            AddressU: D3D11_TEXTURE_ADDRESS_CLAMP,
            AddressV: D3D11_TEXTURE_ADDRESS_CLAMP,
            AddressW: D3D11_TEXTURE_ADDRESS_CLAMP,
            MipLODBias: 0.0,
            MaxAnisotropy: 1,
            ComparisonFunc: D3D11_COMPARISON_NEVER,
            BorderColor: [0.0; 4],
            MinLOD: 0.0,
            MaxLOD: f32::MAX,
        };
        let mut sampler = None;
        // SAFETY: descripción local válida.
        unsafe { device.CreateSamplerState(&sampler_desc, Some(&mut sampler))? };

        let cb_blur = constant_buffer(&device, size_of::<BlurParams>())?;
        let cb_glass = constant_buffer(&device, size_of::<GlassParams>())?;
        let timer = GpuTimer::new(&device)?;

        Ok(Gpu {
            device,
            context,
            winrt_device,
            factory,
            adapter,
            vs: vs.ok_or_else(|| fail("sin vertex shader"))?,
            ps_down: ps_down.ok_or_else(|| fail("sin PSDown"))?,
            ps_up: ps_up.ok_or_else(|| fail("sin PSUp"))?,
            ps_glass: ps_glass.ok_or_else(|| fail("sin PSGlass"))?,
            sampler: sampler.ok_or_else(|| fail("sin sampler"))?,
            cb_blur,
            cb_glass,
            timer,
        })
    }

    /// Cadena de intercambio para composición: alfa premultiplicado por píxel.
    pub fn create_swapchain(&self, width: u32, height: u32) -> Result<IDXGISwapChain1> {
        let desc = DXGI_SWAP_CHAIN_DESC1 {
            Width: width.max(1),
            Height: height.max(1),
            Format: DXGI_FORMAT_B8G8R8A8_UNORM,
            Stereo: false.into(),
            SampleDesc: DXGI_SAMPLE_DESC {
                Count: 1,
                Quality: 0,
            },
            BufferUsage: DXGI_USAGE_RENDER_TARGET_OUTPUT,
            BufferCount: 2,
            Scaling: DXGI_SCALING_STRETCH,
            SwapEffect: DXGI_SWAP_EFFECT_FLIP_SEQUENTIAL,
            AlphaMode: DXGI_ALPHA_MODE_PREMULTIPLIED,
            Flags: 0,
        };
        // SAFETY: dispositivo y descripción válidos.
        unsafe {
            self.factory
                .CreateSwapChainForComposition(&self.device, &desc, None)
        }
    }

    /// Empieza a medir el tiempo de GPU de un fotograma (todas las ventanas juntas).
    pub fn begin_frame(&mut self) {
        self.timer.begin(&self.context);
    }

    /// Termina la medición. Devuelve la media reciente en milisegundos, si ya hay datos.
    pub fn end_frame(&mut self) -> Option<f32> {
        self.timer.end(&self.context)
    }

    /// Desenfoca el nivel 0 de la cadena (lo de detrás, ya copiado) hacia los niveles pequeños.
    pub fn blur(&self, targets: &Targets, levels: usize, offset: f32) {
        let levels = levels.clamp(1, targets.chain.len().saturating_sub(1));
        let ctx = &self.context;
        // SAFETY: todos los recursos pertenecen a este dispositivo y siguen vivos.
        unsafe {
            ctx.IASetPrimitiveTopology(D3D11_PRIMITIVE_TOPOLOGY_TRIANGLELIST);
            ctx.VSSetShader(&self.vs, None);
            ctx.PSSetSamplers(0, Some(&[Some(self.sampler.clone())]));
            ctx.PSSetConstantBuffers(0, Some(&[Some(self.cb_blur.clone())]));

            ctx.PSSetShader(&self.ps_down, None);
            for i in 1..=levels {
                self.blur_pass(&targets.chain[i - 1], &targets.chain[i], offset);
            }
            ctx.PSSetShader(&self.ps_up, None);
            for i in (1..levels).rev() {
                self.blur_pass(&targets.chain[i + 1], &targets.chain[i], offset);
            }
        }
    }

    unsafe fn blur_pass(&self, src: &Texture, dst: &Texture, offset: f32) {
        let params = BlurParams {
            texel: [1.0 / src.width as f32, 1.0 / src.height as f32],
            offset,
            pad: 0.0,
        };
        let ctx = &self.context;
        // SAFETY: lo garantiza quien llama (recursos vivos del mismo dispositivo).
        unsafe {
            // La textura de destino no puede seguir enlazada como entrada.
            ctx.PSSetShaderResources(0, Some(&[None]));
            ctx.UpdateSubresource(
                &self.cb_blur,
                0,
                None,
                &params as *const _ as *const _,
                0,
                0,
            );
            ctx.OMSetRenderTargets(Some(&[Some(dst.rtv.clone())]), None);
            ctx.RSSetViewports(Some(&[viewport(dst.width, dst.height)]));
            ctx.PSSetShaderResources(0, Some(&[Some(src.srv.clone())]));
            ctx.Draw(3, 0);
        }
    }

    /// Dibuja la lámina en la cadena de intercambio y la presenta.
    pub fn draw_glass(&self, targets: &Targets, params: &GlassParams) -> Result<()> {
        let ctx = &self.context;
        // El resultado del desenfoque está en el nivel 1 (mitad de resolución).
        let blurred = targets
            .chain
            .get(1)
            .map(|t| t.srv.clone())
            .or_else(|| targets.chain.first().map(|t| t.srv.clone()));
        // SAFETY: recursos vivos del mismo dispositivo.
        unsafe {
            ctx.IASetPrimitiveTopology(D3D11_PRIMITIVE_TOPOLOGY_TRIANGLELIST);
            ctx.VSSetShader(&self.vs, None);
            ctx.PSSetShader(&self.ps_glass, None);
            ctx.PSSetSamplers(0, Some(&[Some(self.sampler.clone())]));
            ctx.UpdateSubresource(
                &self.cb_glass,
                0,
                None,
                params as *const _ as *const _,
                0,
                0,
            );
            ctx.PSSetConstantBuffers(0, Some(&[Some(self.cb_glass.clone())]));
            ctx.PSSetShaderResources(0, Some(&[None]));
            ctx.OMSetRenderTargets(Some(std::slice::from_ref(&targets.back)), None);
            ctx.RSSetViewports(Some(&[viewport(targets.width, targets.height)]));
            ctx.PSSetShaderResources(0, Some(&[blurred]));
            ctx.Draw(3, 0);
            ctx.PSSetShaderResources(0, Some(&[None]));
            ctx.OMSetRenderTargets(None, None);
            targets.swapchain.Present(0, DXGI_PRESENT(0)).ok()
        }
    }

    /// Copia al nivel 0 de la cadena el trozo de la captura que queda detrás de la ventana.
    /// `src_x`/`src_y`: esquina del área cliente relativa al monitor capturado.
    pub fn copy_backdrop(
        &self,
        targets: &Targets,
        frame: &ID3D11Texture2D,
        frame_size: (u32, u32),
        src_x: i32,
        src_y: i32,
    ) {
        let (fw, fh) = (frame_size.0 as i32, frame_size.1 as i32);
        let (w, h) = (targets.width as i32, targets.height as i32);
        let left = src_x.clamp(0, fw);
        let top = src_y.clamp(0, fh);
        let right = (src_x + w).clamp(0, fw);
        let bottom = (src_y + h).clamp(0, fh);
        if right <= left || bottom <= top {
            return;
        }
        let bx = D3D11_BOX {
            left: left as u32,
            top: top as u32,
            front: 0,
            right: right as u32,
            bottom: bottom as u32,
            back: 1,
        };
        let Some(dst) = targets.chain.first() else {
            return;
        };
        // SAFETY: caja recortada a los dos recursos; mismo formato BGRA.
        unsafe {
            self.context.CopySubresourceRegion(
                &dst.texture,
                0,
                (left - src_x) as u32,
                (top - src_y) as u32,
                0,
                frame,
                0,
                Some(&bx),
            );
        }
    }

    /// (Re)crea las texturas de una ventana para un tamaño dado.
    pub fn resize_targets(&self, targets: &mut Targets, width: u32, height: u32) -> Result<()> {
        let (width, height) = (width.max(1), height.max(1));
        // La vista del búfer trasero debe soltarse antes de redimensionar.
        targets.release_back();
        // SAFETY: no quedan referencias a los búferes de la cadena.
        unsafe {
            self.context.OMSetRenderTargets(None, None);
            self.context.Flush();
            targets.swapchain.ResizeBuffers(
                2,
                width,
                height,
                DXGI_FORMAT_B8G8R8A8_UNORM,
                DXGI_SWAP_CHAIN_FLAG(0),
            )?;
        }
        targets.back = Some(back_buffer_view(&self.device, &targets.swapchain)?);
        targets.width = width;
        targets.height = height;
        targets.chain.clear();
        // Nivel 0: imagen de detrás a tamaño completo; luego mitad, cuarto…
        let (mut w, mut h) = (width, height);
        for _ in 0..=CHAIN_LEVELS {
            targets.chain.push(Texture::new(&self.device, w, h)?);
            w = w.div_ceil(2).max(1);
            h = h.div_ceil(2).max(1);
        }
        Ok(())
    }

    pub fn new_targets(&self, width: u32, height: u32) -> Result<Targets> {
        let swapchain = self.create_swapchain(width, height)?;
        let mut targets = Targets {
            swapchain,
            back: None,
            width: 0,
            height: 0,
            chain: Vec::new(),
        };
        self.resize_targets(&mut targets, width, height)?;
        Ok(targets)
    }
}

/// Niveles de la cadena de desenfoque (hasta 1/32 de resolución).
pub const CHAIN_LEVELS: usize = 5;

/// Recursos de dibujo de una ventana.
pub struct Targets {
    pub swapchain: IDXGISwapChain1,
    /// Vista del búfer trasero; se suelta antes de redimensionar (si no, ResizeBuffers falla).
    back: Option<ID3D11RenderTargetView>,
    pub width: u32,
    pub height: u32,
    chain: Vec<Texture>,
}

impl Targets {
    fn release_back(&mut self) {
        self.back = None;
    }
}

struct Texture {
    texture: ID3D11Texture2D,
    rtv: ID3D11RenderTargetView,
    srv: ID3D11ShaderResourceView,
    width: u32,
    height: u32,
}

impl Texture {
    fn new(device: &ID3D11Device, width: u32, height: u32) -> Result<Texture> {
        let desc = D3D11_TEXTURE2D_DESC {
            Width: width,
            Height: height,
            MipLevels: 1,
            ArraySize: 1,
            Format: DXGI_FORMAT_B8G8R8A8_UNORM,
            SampleDesc: DXGI_SAMPLE_DESC {
                Count: 1,
                Quality: 0,
            },
            Usage: D3D11_USAGE_DEFAULT,
            BindFlags: (D3D11_BIND_RENDER_TARGET.0 | D3D11_BIND_SHADER_RESOURCE.0) as u32,
            CPUAccessFlags: 0,
            MiscFlags: 0,
        };
        let mut texture = None;
        let mut rtv = None;
        let mut srv = None;
        // SAFETY: descripción local válida; punteros de salida locales.
        unsafe {
            device.CreateTexture2D(&desc, None, Some(&mut texture))?;
            let texture = texture.as_ref().ok_or_else(|| fail("sin textura"))?;
            device.CreateRenderTargetView(texture, None, Some(&mut rtv))?;
            device.CreateShaderResourceView(texture, None, Some(&mut srv))?;
        }
        Ok(Texture {
            texture: texture.ok_or_else(|| fail("sin textura"))?,
            rtv: rtv.ok_or_else(|| fail("sin RTV"))?,
            srv: srv.ok_or_else(|| fail("sin SRV"))?,
            width,
            height,
        })
    }
}

/// Mide el tiempo de GPU con consultas de marca de tiempo, leídas fotogramas después para
/// no parar la GPU esperando.
struct GpuTimer {
    free: Vec<[ID3D11Query; 3]>,
    pending: VecDeque<[ID3D11Query; 3]>,
    current: Option<[ID3D11Query; 3]>,
    recent: VecDeque<f32>,
}

impl GpuTimer {
    fn new(device: &ID3D11Device) -> Result<GpuTimer> {
        let mut free = Vec::new();
        for _ in 0..4 {
            free.push([
                query(device, D3D11_QUERY_TIMESTAMP_DISJOINT)?,
                query(device, D3D11_QUERY_TIMESTAMP)?,
                query(device, D3D11_QUERY_TIMESTAMP)?,
            ]);
        }
        Ok(GpuTimer {
            free,
            pending: VecDeque::new(),
            current: None,
            recent: VecDeque::new(),
        })
    }

    fn begin(&mut self, ctx: &ID3D11DeviceContext) {
        let Some(set) = self.free.pop() else {
            return;
        };
        // SAFETY: consultas de este dispositivo.
        unsafe {
            ctx.Begin(&set[0]);
            ctx.End(&set[1]);
        }
        self.current = Some(set);
    }

    fn end(&mut self, ctx: &ID3D11DeviceContext) -> Option<f32> {
        if let Some(set) = self.current.take() {
            // SAFETY: consultas de este dispositivo, empezadas en begin().
            unsafe {
                ctx.End(&set[2]);
                ctx.End(&set[0]);
            }
            self.pending.push_back(set);
        }
        // Recoge las que ya estén listas, sin esperar.
        while let Some(set) = self.pending.front() {
            let mut disjoint = D3D11_QUERY_DATA_TIMESTAMP_DISJOINT::default();
            let (mut t0, mut t1) = (0u64, 0u64);
            // SAFETY: tamaños de los tipos que devuelve cada consulta.
            let ready = unsafe {
                ctx.GetData(
                    &set[0],
                    Some(&mut disjoint as *mut _ as *mut _),
                    size_of::<D3D11_QUERY_DATA_TIMESTAMP_DISJOINT>() as u32,
                    D3D11_ASYNC_GETDATA_DONOTFLUSH.0 as u32,
                )
                .is_ok()
                    && ctx
                        .GetData(
                            &set[1],
                            Some(&mut t0 as *mut _ as *mut _),
                            8,
                            D3D11_ASYNC_GETDATA_DONOTFLUSH.0 as u32,
                        )
                        .is_ok()
                    && ctx
                        .GetData(
                            &set[2],
                            Some(&mut t1 as *mut _ as *mut _),
                            8,
                            D3D11_ASYNC_GETDATA_DONOTFLUSH.0 as u32,
                        )
                        .is_ok()
            };
            // GetData devuelve S_FALSE (Ok) mientras no hay datos: la frecuencia sigue a 0.
            if !ready || disjoint.Frequency == 0 {
                if self.pending.len() < 4 {
                    break;
                }
                // Demasiadas pendientes: se descarta la más antigua.
            } else if !disjoint.Disjoint.as_bool() && t1 >= t0 {
                let ms = (t1 - t0) as f64 * 1000.0 / disjoint.Frequency as f64;
                self.recent.push_back(ms as f32);
                if self.recent.len() > 60 {
                    self.recent.pop_front();
                }
            }
            if let Some(set) = self.pending.pop_front() {
                self.free.push(set);
            }
        }
        (!self.recent.is_empty())
            .then(|| self.recent.iter().sum::<f32>() / self.recent.len() as f32)
    }
}

fn query(
    device: &ID3D11Device,
    kind: windows::Win32::Graphics::Direct3D11::D3D11_QUERY,
) -> Result<ID3D11Query> {
    let desc = D3D11_QUERY_DESC {
        Query: kind,
        MiscFlags: 0,
    };
    let mut q = None;
    // SAFETY: descripción local válida.
    unsafe { device.CreateQuery(&desc, Some(&mut q))? };
    q.ok_or_else(|| fail("sin consulta"))
}

fn constant_buffer(device: &ID3D11Device, size: usize) -> Result<ID3D11Buffer> {
    let desc = D3D11_BUFFER_DESC {
        ByteWidth: size.next_multiple_of(16) as u32,
        Usage: D3D11_USAGE_DEFAULT,
        BindFlags: D3D11_BIND_CONSTANT_BUFFER.0 as u32,
        CPUAccessFlags: 0,
        MiscFlags: 0,
        StructureByteStride: 0,
    };
    let mut buffer = None;
    // SAFETY: descripción local válida.
    unsafe { device.CreateBuffer(&desc, None, Some(&mut buffer))? };
    buffer.ok_or_else(|| fail("sin búfer de constantes"))
}

fn back_buffer_view(
    device: &ID3D11Device,
    swapchain: &IDXGISwapChain1,
) -> Result<ID3D11RenderTargetView> {
    let mut rtv = None;
    // SAFETY: el búfer 0 existe en toda cadena de intercambio.
    unsafe {
        let back: ID3D11Texture2D = swapchain.GetBuffer(0)?;
        device.CreateRenderTargetView(&back, None, Some(&mut rtv))?;
    }
    rtv.ok_or_else(|| fail("sin vista del búfer trasero"))
}

fn viewport(width: u32, height: u32) -> D3D11_VIEWPORT {
    D3D11_VIEWPORT {
        TopLeftX: 0.0,
        TopLeftY: 0.0,
        Width: width as f32,
        Height: height as f32,
        MinDepth: 0.0,
        MaxDepth: 1.0,
    }
}

/// Compila un programa de glass.hlsl con el compilador de Windows (d3dcompiler_47.dll).
fn compile(entry: PCSTR, target: PCSTR) -> Result<Vec<u8>> {
    let mut code: Option<ID3DBlob> = None;
    let mut errors: Option<ID3DBlob> = None;
    // SAFETY: el texto y su longitud vienen del mismo &str; punteros de salida locales.
    let result = unsafe {
        D3DCompile(
            SHADERS.as_ptr() as *const _,
            SHADERS.len(),
            s!("glass.hlsl"),
            None,
            None::<&ID3DInclude>,
            entry,
            target,
            D3DCOMPILE_OPTIMIZATION_LEVEL3,
            0,
            &mut code,
            Some(&mut errors),
        )
    };
    if let Err(err) = result {
        let detail = errors
            .map(|b| blob_bytes(&b))
            .map(|b| String::from_utf8_lossy(&b).into_owned());
        return Err(fail(&format!(
            "shader: {err} {}",
            detail.unwrap_or_default()
        )));
    }
    code.map(|b| blob_bytes(&b))
        .ok_or_else(|| fail("shader vacío"))
}

fn blob_bytes(blob: &ID3DBlob) -> Vec<u8> {
    // SAFETY: el blob es dueño del búfer durante esta llamada.
    unsafe {
        std::slice::from_raw_parts(blob.GetBufferPointer() as *const u8, blob.GetBufferSize())
            .to_vec()
    }
}

pub fn fail(msg: &str) -> Error {
    Error::new(E_FAIL, msg)
}
