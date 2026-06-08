"""
Halfcab v2 — ML-Enhanced SDR→HDR via Gain Map Prediction (GMNet)

Architecture: gain map inverse tone mapping.
  HDR_linear = SDR_linear × peak^(gainmap - 1)
where the network predicts a per-pixel gain map [0,1].

This is the gain-map approach (GMNet, ICLR 2025 "Learning Gain Map for
Inverse Tone Mapping"). The network decides per-pixel how much of the
HDR peak each region deserves — light sources reach toward peak nits,
midtones sit near reference white. This genuinely redistributes
luminance into HDR range, unlike a global curve.

Model: pure PyTorch CNN (Conv/ReLU/PixelShuffle) — runs on MPS/CPU/CUDA.
Weights: ml_models/GMNet/checkpoints/G_synthetic.pth  (peak 8.0)
         ml_models/GMNet/checkpoints/G_realworld.pth  (peak 5.0)
"""

import os, sys, io, subprocess, json, math, tempfile, glob, types
os.environ.setdefault('OPENCV_IO_ENABLE_OPENEXR', '1')   # enable EXR before cv2 import
import numpy as np

GMNET_DIR  = os.path.join(os.path.dirname(__file__), '..', 'ml_models', 'GMNet')
CODES_DIR  = os.path.join(GMNET_DIR, 'codes')
CKPT_SYN   = os.path.join(GMNET_DIR, 'checkpoints', 'G_synthetic.pth')
CKPT_REAL  = os.path.join(GMNET_DIR, 'checkpoints', 'G_realworld.pth')

FFMPEG  = 'ffmpeg'
FFPROBE = 'ffprobe'

_model = None
_model_device = None


def _load_gmnet(device):
    """Load the GMNet generator standalone (no BasicSR framework)."""
    global _model, _model_device
    if _model is not None and _model_device == device:
        return _model

    import torch

    # Stub the gpu_memory_log import GMNet.py expects
    if 'utils.gpu_memory_log' not in sys.modules:
        stub = types.ModuleType('utils.gpu_memory_log')
        stub.gpu_memory_log = lambda *a, **k: None
        sys.modules['utils'] = types.ModuleType('utils')
        sys.modules['utils.gpu_memory_log'] = stub

    # Make `models.modules.arch_util` importable
    sys.path.insert(0, CODES_DIR)
    import models.modules.GMNet as gmnet_mod   # noqa: E402

    net = gmnet_mod.GMNet(in_nc=3, out_nc=1, nf=64, nb=16, act_type='relu')
    state = torch.load(CKPT_SYN, map_location='cpu', weights_only=False)
    net.load_state_dict(state, strict=False)
    net = net.to(device).eval()

    _model = net
    _model_device = device
    print(f'[ml_enhance] GMNet loaded on {device}', flush=True)
    return net


def infer_gainmap(frame_rgb_uint8, device, net, thumb=384):
    """
    Predict the gain map for one SDR frame.

    frame_rgb_uint8: (H, W, 3) uint8
    returns: gainmap (H, W) float32 in [0, ~1] — per-pixel HDR gain
    """
    import torch
    import torch.nn.functional as F

    h, w = frame_rgb_uint8.shape[:2]
    sdr = torch.from_numpy(frame_rgb_uint8.astype(np.float32) / 255.0)
    sdr = sdr.permute(2, 0, 1).unsqueeze(0).to(device)   # (1,3,H,W)

    # Local branch: full-res SDR (pad to multiple of 2 for PixelShuffle)
    pad_h = (2 - h % 2) % 2
    pad_w = (2 - w % 2) % 2
    local = F.pad(sdr, (0, pad_w, 0, pad_h), mode='reflect') if (pad_h or pad_w) else sdr

    # Global branch: downsampled "thumbnail" giving the network global context
    global_ctx = F.interpolate(sdr, size=(thumb, thumb), mode='bilinear', align_corners=False)

    with torch.no_grad():
        _, gain_q = net((local, global_ctx))   # gain_q = qmax * normalized_gainmap

    gain = torch.clamp(gain_q, 0, None)         # (1,1,H',W')
    # Upsample gain map to full frame size (bicubic = smoother than bilinear)
    gain = F.interpolate(gain, size=(h, w), mode='bicubic', align_corners=False)
    gain = torch.clamp(gain, 0, None)
    return gain.squeeze(0).squeeze(0).cpu().numpy().astype(np.float32)


# ─── Color science (numpy — no zscale dependency) ─────────────────────────

# Rec.709 → Rec.2020 primary conversion (linear RGB, BT.2087)
_R709_TO_R2020 = np.array([
    [0.6274039, 0.3292830, 0.0433131],
    [0.0690973, 0.9195404, 0.0113623],
    [0.0163914, 0.0880133, 0.8955953],
], dtype=np.float32)

# Rec.709 (linear) → ACEScg (AP1 primaries, linear) — standard ACES IDT matrix.
# This is what a VFX/Nuke/Resolve ACES pipeline expects for incoming plates.
_R709_TO_ACESCG = np.array([
    [0.6130974, 0.3395229, 0.0473793],
    [0.0701933, 0.9163556, 0.0134511],
    [0.0206156, 0.1095698, 0.8698151],
], dtype=np.float32)

# HLG OETF constants (BT.2100 / ARIB STD-B67)
_HLG_A, _HLG_B, _HLG_C = 0.17883277, 0.28466892, 0.55991073

# Scene-linear value (in our 1.0=SDR-ref-white space) that maps to HLG
# reference white (signal 0.75). Derived: solve OETF(x)=0.75 → x≈0.265.
_HLG_REF_SCALE = 0.265


def _hlg_oetf(E):
    E = np.clip(E, 0.0, 1.0)
    return np.where(E <= 1.0/12.0,
                    np.sqrt(3.0 * E),
                    _HLG_A * np.log(np.maximum(12.0 * E - _HLG_B, 1e-6)) + _HLG_C)


def sdr_to_hdr(frame_rgb_uint8, gainmap, peak=8.0, dither=True):
    """
    Gain-map SDR→HDR producing scene-linear Rec.709 HDR (Ultra-HDR style).

    HDR_linear = SDR_linear × peak^gainmap

    Preserves the SDR base (gain=0 → unchanged), boosts flagged regions
    up to peak× brighter. 1.0 = SDR reference white; values above are
    genuine HDR headroom. Returns (H,W,3) float32 linear Rec.709.

    Dithering: the 8-bit source has only ~256 code values. When a smooth
    gradient is expanded into the wider HDR range, the gaps between codes
    become visible as banding. We add triangular (TPDF) dither of ±0.5
    code step in the gamma domain *before* linearizing — this breaks the
    source quantisation into imperceptible noise the eye averages out,
    so the expansion has continuous values to work with.
    """
    sdr = frame_rgb_uint8.astype(np.float32) / 255.0
    if dither:
        step = 1.0 / 255.0
        tpdf = (np.random.random(sdr.shape).astype(np.float32) -
                np.random.random(sdr.shape).astype(np.float32))   # [-1,1] triangular
        sdr = np.clip(sdr + tpdf * step * 0.5, 0.0, 1.0)
    sdr_lin = np.power(sdr, 2.2)
    g = np.clip(gainmap, 0, 1)[..., None]
    hdr = sdr_lin * np.power(peak, g)
    return np.clip(hdr, 0, 12.0).astype(np.float32)


def hdr_linear_to_hlg(hdr_lin_709):
    """
    Convert scene-linear Rec.709 HDR → HLG-encoded Rec.2020 signal [0,1].

    1. Rec.709 → Rec.2020 primaries (linear matrix)
    2. Scale so SDR ref white (1.0) → HLG scene-linear 0.265
    3. HLG OETF → signal where ref white = 0.75, highlights above
    Returns (H,W,3) float32 in [0,1].
    """
    h, w, _ = hdr_lin_709.shape
    flat = hdr_lin_709.reshape(-1, 3)
    r2020 = flat @ _R709_TO_R2020.T
    r2020 = np.clip(r2020, 0, None).reshape(h, w, 3)
    signal = _hlg_oetf(r2020 * _HLG_REF_SCALE)
    return np.clip(signal, 0, 1).astype(np.float32)


def hdr_linear_to_graded(hdr_lin_709, knee=0.80, gamma=2.4):
    """
    Convert scene-linear Rec.709 HDR → a CLEANLY-EXPOSED Rec.709 video
    signal [0,1] with a smooth highlight shoulder — no clamping, no banding,
    headroom for grading.

    Kept in Rec.709 primaries (NOT Rec.2020) so it behaves predictably in
    ANY sequence — an HLG/2020 sequence would otherwise remap the white
    point and crush the highlights to ~75 IRE. This is a clean gradeable
    SDR-gamut master; the recovered highlight detail is its value.

    Tone curve: values below `knee` pass 1:1 (exposure preserved), values
    above (the overbright the gain map recovered) roll smoothly into the
    [knee,1] headroom via a tanh shoulder — graceful falloff, not a clip.
    """
    x = np.clip(hdr_lin_709, 0, None)   # stay in Rec.709 linear
    rolled = np.where(
        x <= knee,
        x,
        knee + (1.0 - knee) * np.tanh((x - knee) / (1.0 - knee))
    )
    rolled = np.clip(rolled, 0, 1)
    signal = np.power(rolled, 1.0 / gamma)   # gamma 2.4 encode
    return signal.astype(np.float32)


def hdr_linear_to_acescg(hdr_lin_709):
    """
    Convert scene-linear Rec.709 HDR → ACEScg (AP1 primaries, linear).
    Overbright values (>1.0) preserved — for VFX/Nuke/Resolve ACES pipelines.
    """
    h, w, _ = hdr_lin_709.shape
    acescg = (hdr_lin_709.reshape(-1, 3) @ _R709_TO_ACESCG.T).reshape(h, w, 3)
    return np.clip(acescg, 0, None).astype(np.float32)


# ─── Video helpers ─────────────────────────────────────────────────────────

def get_video_info(path):
    cmd = [FFPROBE, '-v', 'quiet', '-print_format', 'json',
           '-show_streams', '-show_format', path]
    d = json.loads(subprocess.run(cmd, capture_output=True, text=True).stdout)
    vs = next(s for s in d['streams'] if s['codec_type'] == 'video')
    fps_n, fps_d = vs['r_frame_rate'].split('/')
    return {
        'width': vs['width'], 'height': vs['height'],
        'fps': float(fps_n) / float(fps_d),
        'duration': float(d['format']['duration']),
    }


def _ml_convert_exr(src, out_dir, colorspace='rec709', weights_path=None, progress_cb=None):
    """
    Scene-linear EXR sequence for compositing (After Effects / Nuke / Resolve).

    Writes numbered .exr frames carrying genuine scene-linear HDR:
      1.0 = diffuse/SDR reference white
      >1.0 = overbright lights, specular, highlights (lamp ≈ 2.5)

    colorspace:
      'rec709' → linear Rec.709 primaries  (After Effects default linear comp)
      'acescg' → ACEScg / AP1 primaries    (VFX/Nuke/Resolve ACES pipeline)
    """
    import torch, cv2
    from PIL import Image

    device = (torch.device('mps') if torch.backends.mps.is_available()
              else torch.device('cuda') if torch.cuda.is_available()
              else torch.device('cpu'))
    print(f'[ml_enhance] EXR mode ({colorspace}), device: {device}', flush=True)

    net  = _load_gmnet(device)
    info = get_video_info(src)
    w, h = info['width'], info['height']

    base = os.path.splitext(os.path.basename(src))[0]
    seq_dir = out_dir if (os.path.isdir(out_dir) or not os.path.splitext(out_dir)[1]) \
              else os.path.splitext(out_dir)[0]
    os.makedirs(seq_dir, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        in_pat = os.path.join(tmp, 'in_%06d.png')
        subprocess.run([FFMPEG, '-y', '-i', src,
                        '-vf', f'scale={w}:{h},gradfun=strength=1.5:radius=16,format=rgb24',
                        in_pat], check=True, capture_output=True)
        frames = sorted(glob.glob(os.path.join(tmp, 'in_*.png')))
        total = len(frames)
        print(f'[ml_enhance] {total} frames → EXR ({colorspace})', flush=True)

        import OpenImageIO as oiio
        # Chromaticities tags (R x,y  G x,y  B x,y  W x,y) so Nuke/Resolve/AE
        # read the correct primaries instead of assuming sRGB.
        CHROMA = {
            'rec709': (0.640, 0.330, 0.300, 0.600, 0.150, 0.060, 0.3127, 0.3290),
            'acescg': (0.713, 0.293, 0.165, 0.830, 0.128, 0.044, 0.32168, 0.33767),
        }[colorspace]

        for i, fp in enumerate(frames):
            rgb  = np.array(Image.open(fp).convert('RGB'), dtype=np.uint8)
            gain = infer_gainmap(rgb, device, net)
            hdr  = sdr_to_hdr(rgb, gain, peak=8.0)        # scene-linear Rec.709 [0,12]
            if colorspace == 'acescg':
                hdr = hdr_linear_to_acescg(hdr)            # → AP1 primaries

            # Write tagged float EXR via OpenImageIO (chromaticities embedded)
            spec = oiio.ImageSpec(hdr.shape[1], hdr.shape[0], 3, 'float')
            spec.attribute('chromaticities', 'float[8]', CHROMA)
            spec.attribute('compression', 'zip')
            spec.attribute('oiio:ColorSpace',
                           'ACEScg' if colorspace == 'acescg' else 'Linear Rec.709')
            ibuf = oiio.ImageBuf(spec)
            ibuf.set_pixels(oiio.ROI(0, hdr.shape[1], 0, hdr.shape[0], 0, 1, 0, 3),
                            np.ascontiguousarray(hdr, dtype=np.float32))
            ibuf.write(os.path.join(seq_dir, f'{base}_{i+1:06d}.exr'))

            if progress_cb:
                progress_cb(i + 1, total)

    print(f'[ml_enhance] done → {seq_dir}/ ({total} EXR frames, {colorspace})', flush=True)
    return seq_dir


def ml_convert(src, out_path, peak_nits=1000, weights_path=None,
               output_format='prores', progress_cb=None):
    """
    Full ML gain-map SDR→HDR conversion.

    output_format:
      'prores'        → HLG Rec.2020 ProRes — true HDR video (Premiere/broadcast).
                        HDR lives in the HLG curve; signal is [0,1].
      'graded'        → Rec.2020 ProRes with HDR-informed filmic shoulder.
                        Cleanly exposed [0,1], smooth highlights, NO banding,
                        headroom for grading. Uses the HDR reconstruction to
                        improve exposure without forcing overbright.
      'exr'           → scene-linear EXR, Rec.709 (After Effects 32bpc comp).
      'exr_acescg'    → scene-linear EXR, ACEScg/AP1 (VFX/Nuke/Resolve ACES).
    """
    import torch
    from PIL import Image

    if output_format == 'exr':
        return _ml_convert_exr(src, out_path, 'rec709', weights_path, progress_cb)
    if output_format == 'exr_acescg':
        return _ml_convert_exr(src, out_path, 'acescg', weights_path, progress_cb)

    if torch.backends.mps.is_available():
        device = torch.device('mps')
    elif torch.cuda.is_available():
        device = torch.device('cuda')
    else:
        device = torch.device('cpu')
    print(f'[ml_enhance] device: {device}', flush=True)

    import cv2

    net  = _load_gmnet(device)
    info = get_video_info(src)
    w, h, fps = info['width'], info['height'], info['fps']

    # Gain-map model peak factor (G_synthetic trained with peak=8.0)
    model_peak = 8.0

    with tempfile.TemporaryDirectory() as tmp:
        in_pat  = os.path.join(tmp, 'in_%06d.png')
        out_pat = os.path.join(tmp, 'hlg_%06d.png')

        # Extract frames with debanding. gradfun smooths the 8-bit source
        # gradients (lamp glows, sky) BEFORE the HDR expansion amplifies the
        # quantisation steps into visible bands. Applied in the source gamma
        # domain where the banding originates. radius 16 covers soft halos.
        subprocess.run([FFMPEG, '-y', '-i', src,
                        '-vf', f'scale={w}:{h},gradfun=strength=1.5:radius=16,'
                               f'format=rgb24', in_pat],
                       check=True, capture_output=True)
        frames = sorted(glob.glob(os.path.join(tmp, 'in_*.png')))
        total = len(frames)
        print(f'[ml_enhance] {total} frames', flush=True)

        graded = (output_format == 'graded')
        for i, fp in enumerate(frames):
            rgb    = np.array(Image.open(fp).convert('RGB'), dtype=np.uint8)
            gain   = infer_gainmap(rgb, device, net)
            hdr    = sdr_to_hdr(rgb, gain, peak=model_peak)  # linear Rec.709 [0,12]
            if graded:
                signal = hdr_linear_to_graded(hdr)           # filmic shoulder, gamma 2.4
            else:
                signal = hdr_linear_to_hlg(hdr)              # HLG signal [0,1]

            # Final TPDF dither at 16-bit quantisation. cv2 expects BGR uint16.
            tpdf = (np.random.random(signal.shape).astype(np.float32) -
                    np.random.random(signal.shape).astype(np.float32))
            sig16 = np.clip(signal * 65535.0 + tpdf * 0.5, 0, 65535).astype(np.uint16)
            cv2.imwrite(os.path.join(tmp, f'hlg_{i+1:06d}.png'), sig16[:, :, ::-1])

            if progress_cb:
                progress_cb(i + 1, total)

        os.makedirs(os.path.dirname(out_path) or '.', exist_ok=True)
        print('[ml_enhance] encoding …', flush=True)

        # graded mode: Rec.709 gamma-2.4 — predictable gradeable SDR-gamut
        #              master, behaves correctly in ANY sequence (no remap crush)
        # prores mode: Rec.2020 HLG — true HDR curve
        if graded:
            prim, trc, mtx = 'bt709', 'bt709', 'bt709'
        else:
            prim, trc, mtx = 'bt2020', 'arib-std-b67', 'bt2020nc'
        subprocess.run([
            FFMPEG, '-y',
            '-framerate', str(fps),
            '-i', out_pat,
            '-i', src, '-map', '0:v', '-map', '1:a?',
            '-vf', f'setparams=color_primaries={prim}:color_trc={trc}:'
                   f'colorspace={mtx},format=yuv444p12le',
            '-c:v', 'prores_ks', '-profile:v', '4444', '-pix_fmt', 'yuva444p12le',
            '-color_primaries', prim, '-color_trc', trc, '-colorspace', mtx,
            '-c:a', 'copy', out_path,
        ], check=True, capture_output=True)

    print(f'[ml_enhance] done → {out_path}', flush=True)
    return out_path


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print('Usage: python ml_enhance.py <in.mp4> <out.mov>'); sys.exit(1)
    ml_convert(sys.argv[1], sys.argv[2],
               progress_cb=lambda d, t: print(f'  {d}/{t}', end='\r', flush=True))
    print('\nDone.')
