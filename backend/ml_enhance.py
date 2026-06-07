"""
Halfcab v2 — ML Enhancement via ITMLUT
Inverse tone mapping using a pretrained 3D LUT network.

Replaces ITMLUT's CUDA-only ailut_transform with a pure PyTorch
implementation that runs on CPU and Apple Silicon MPS.

Model: ITMLUT (CVMP 2023 / SIGGRAPH)
Weights: ml_models/ITMLUT/params.pth  (trained on HDRTV4K)
         ml_models/ITMLUT/params_TV1K.pth (trained on HDRTV1K)

Output: float32 HDR values, potentially > 1.0 where the model
        predicts overbright regions (lamps, specular, sky highlights).
"""

import os, sys, io, subprocess, json, math, tempfile, glob
import numpy as np

MODEL_DIR  = os.path.join(os.path.dirname(__file__), '..', 'ml_models', 'ITMLUT')
WEIGHTS    = os.path.join(MODEL_DIR, 'params.pth')
WEIGHTS_TV = os.path.join(MODEL_DIR, 'params_TV1K.pth')

# ─── Pure-PyTorch ailut_transform replacement ────────────────────────────────

def ailut_transform_pytorch(img, lut, vertices):
    """
    Drop-in replacement for the CUDA ailut_transform extension.
    Works on CPU, MPS (Apple Silicon), and CUDA.

    img:      (B, 3, H, W) float32 in [0,1]
    lut:      (B, 3, D, D, D) float32   — HDR output values at LUT nodes
    vertices: (B, 3, D) float32         — adaptive sample coords in [0,1]
    returns:  (B, 3, H, W) float32
    """
    import torch
    import torch.nn.functional as F

    B, C, H, W = img.shape
    D           = lut.shape[-1]
    device      = img.device

    outputs = []
    for b in range(B):
        verts = vertices[b]   # (3, D)  sample coordinates per channel
        img_b = img[b]        # (3, H, W)

        # Map each pixel value to a fractional LUT index using the adaptive vertices
        frac_lut = torch.zeros(3, H*W, device=device)
        for c in range(3):
            vals = img_b[c].reshape(-1)          # (H*W,)
            v    = verts[c].contiguous()          # (D,)

            # searchsorted: idx[i] = first position in v where v[idx] > vals[i]
            idx = torch.searchsorted(v, vals.contiguous()).clamp(1, D-1)
            i0  = idx - 1
            i1  = idx
            v0  = v[i0]; v1 = v[i1]
            span = (v1 - v0).clamp(min=1e-7)
            frac = (vals - v0) / span             # fraction within the cell [0,1]
            frac_lut[c] = i0.float() + frac       # fractional index in [0, D-1]

        # Convert fractional LUT indices → grid_sample coords in [-1, 1]
        # grid_sample maps -1 → index 0, +1 → index D-1
        grid_coords = frac_lut / (D - 1) * 2.0 - 1.0   # (3, H*W)

        # Rearrange for 3D grid_sample
        # input:  (N=1, C=3, D, D, D)
        # grid:   (N=1, D_out=1, H_out=H, W_out=W, 3)
        # grid[..., 0] → W dim of lut (B channel)
        # grid[..., 1] → H dim of lut (G channel)
        # grid[..., 2] → D dim of lut (R channel)
        r_g = grid_coords[0].reshape(1, H, W)   # R coords
        g_g = grid_coords[1].reshape(1, H, W)   # G coords
        b_g = grid_coords[2].reshape(1, H, W)   # B coords
        # Stack as (x,y,z) = (B,G,R) for LUT dim ordering (D,D,D) = (R,G,B)
        grid = torch.stack([b_g, g_g, r_g], dim=-1)  # (1,H,W,3)
        grid = grid.unsqueeze(1)                       # (1,1,H,W,3)

        out = F.grid_sample(
            lut[b:b+1].float(),   # (1, 3, D, D, D)
            grid.float(),
            mode='bilinear',
            padding_mode='border',
            align_corners=True
        )
        outputs.append(out.squeeze(2))   # (1, 3, H, W)

    return torch.cat(outputs, dim=0)


def patch_ailut():
    """Monkey-patch the ailut module before ITMLUT imports it."""
    import types
    fake = types.ModuleType('ailut')
    fake.ailut_transform = ailut_transform_pytorch
    fake.lut_transform   = ailut_transform_pytorch   # fallback
    sys.modules['ailut'] = fake


# ─── Model loader ─────────────────────────────────────────────────────────────

_model = None   # cached

def get_model(device, weights_path=None):
    global _model
    if _model is not None:
        return _model

    import torch

    patch_ailut()               # must happen before importing network
    sys.path.insert(0, MODEL_DIR)
    from network import LutNet  # noqa: E402

    weights = weights_path or WEIGHTS
    if not os.path.exists(weights):
        raise FileNotFoundError(f'Weights not found: {weights}\n'
                                f'Clone ITMLUT into ml_models/ITMLUT and ensure params.pth is present.')

    net = LutNet()
    state = torch.load(weights, map_location='cpu', weights_only=False)
    net.load_state_dict(state)
    net = net.to(device)
    net.eval()
    _model = net
    print(f'[ml_enhance] LutNet loaded on {device}', flush=True)
    return net


# ─── Per-frame inference ──────────────────────────────────────────────────────

def infer_frame(frame_rgb_uint8, device, net):
    """
    Run the ITMLUT model on a single uint8 RGB frame.

    frame_rgb_uint8: (H, W, 3) numpy array, dtype uint8
    returns: (H, W, 3) numpy float32 — HDR values, possibly > 1.0
    """
    import torch

    h, w = frame_rgb_uint8.shape[:2]
    inp = torch.from_numpy(frame_rgb_uint8.copy()).float() / 255.0  # (H, W, 3) [0,1]
    inp = inp.permute(2, 0, 1).unsqueeze(0).to(device)        # (1, 3, H, W)

    # Pad to multiples of 8 to avoid size mismatches in the pooling layers
    pad_h = (8 - h % 8) % 8
    pad_w = (8 - w % 8) % 8
    if pad_h or pad_w:
        import torch.nn.functional as F
        inp = F.pad(inp, (0, pad_w, 0, pad_h), mode='reflect')

    with torch.no_grad():
        # Patch the model's internal device ref to match our device
        net.device = device
        for attr in ('lut_gen_b', 'lut_gen_m', 'lut_gen_d'):
            module = getattr(net, attr)
            if hasattr(module, 'device'):
                module.device = device

        out = net(inp)   # (1, 3, H+pad, W+pad)

    # Crop padding
    out = out[:, :, :h, :w]
    out_np = out.squeeze(0).permute(1, 2, 0).cpu().numpy()   # (H, W, 3)
    return out_np.astype(np.float32)


# ─── Video processing ─────────────────────────────────────────────────────────

FFMPEG = 'ffmpeg'
FFPROBE = 'ffprobe'


def get_video_info(path):
    cmd = [FFPROBE, '-v', 'quiet', '-print_format', 'json',
           '-show_streams', '-show_format', path]
    r = subprocess.run(cmd, capture_output=True, text=True)
    d = json.loads(r.stdout)
    vs = next(s for s in d['streams'] if s['codec_type'] == 'video')
    duration = float(d['format']['duration'])
    fps_parts = vs['r_frame_rate'].split('/')
    fps = float(fps_parts[0]) / float(fps_parts[1])
    return {
        'width':    vs['width'],
        'height':   vs['height'],
        'fps':      fps,
        'duration': duration,
        'n_frames': int(round(fps * duration)),
    }


def ml_convert(src, out_path, preset_id='prores', peak_nits=1000,
               weights_path=None, progress_cb=None):
    """
    Full ML-enhanced SDR → HDR conversion.

    1. Extract frames from source video (FFmpeg → raw RGB pipe)
    2. Run ITMLUT inverse tone mapping on each frame (PyTorch on MPS/CPU)
    3. Apply HDR headroom scaling (map model output to target peak nits)
    4. Re-encode to ProRes 4444 (FFmpeg)

    progress_cb(done, total) called after each frame if provided.
    """
    import torch
    from PIL import Image

    # Choose device
    if torch.backends.mps.is_available():
        device = torch.device('mps')
    elif torch.cuda.is_available():
        device = torch.device('cuda')
    else:
        device = torch.device('cpu')

    print(f'[ml_enhance] using device: {device}', flush=True)

    net  = get_model(device, weights_path)
    info = get_video_info(src)
    w, h = info['width'], info['height']
    fps  = info['fps']
    n    = info['n_frames']

    # Work in a temp dir
    with tempfile.TemporaryDirectory() as tmpdir:
        frames_in  = os.path.join(tmpdir, 'in_%06d.png')
        frames_out = os.path.join(tmpdir, 'hdr_%06d.ppm')

        # ── Extract all frames ──────────────────────────────────────────
        print(f'[ml_enhance] extracting {n} frames …', flush=True)
        subprocess.run([
            FFMPEG, '-y', '-i', src,
            '-vf', f'scale={w}:{h},format=rgb24',
            '-compression_algo', 'raw',
            frames_in,
        ], check=True, capture_output=True)

        frame_files = sorted(glob.glob(os.path.join(tmpdir, 'in_*.png')))
        n_actual = len(frame_files)
        print(f'[ml_enhance] processing {n_actual} frames …', flush=True)

        # ── Run model frame-by-frame ────────────────────────────────────
        # Headroom scale: map model output to [0, peak_nits/203] in linear
        # SDR reference white = 203 nits → model output of 1.0 = 203 nits
        headroom = peak_nits / 203.0

        for i, fpath in enumerate(frame_files):
            # Load frame
            img_pil = Image.open(fpath).convert('RGB')
            img_np  = np.array(img_pil, dtype=np.uint8)

            # Run inference — output may exceed 1.0 at bright areas
            hdr_np = infer_frame(img_np, device, net)

            # Scale to target headroom and tone-map back to [0,1] for 16-bit storage
            # Reinhard: out = hdr / (1 + hdr/peak) — preserves relative brightness
            hdr_scaled = hdr_np * headroom
            hdr_display = hdr_scaled / (1.0 + hdr_scaled / headroom)
            hdr_display = np.clip(hdr_display, 0, 1)

            # Save as 16-bit PPM — binary format FFmpeg reads natively
            # (PIL can't handle uint16 RGB; PPM avoids any extra dependencies)
            out_fpath = os.path.join(tmpdir, f'hdr_{i+1:06d}.ppm')
            hdr_16 = (hdr_display * 65535).astype(np.uint16)
            with open(out_fpath, 'wb') as pf:
                pf.write(f'P6\n{w} {h}\n65535\n'.encode())
                pf.write(hdr_16.astype('>u2').tobytes())   # big-endian per PPM spec

            if progress_cb:
                progress_cb(i + 1, n_actual)

        # ── Re-encode to ProRes 4444 ───────────────────────────────────
        print('[ml_enhance] encoding …', flush=True)
        os.makedirs(os.path.dirname(out_path) or '.', exist_ok=True)

        subprocess.run([
            FFMPEG, '-y',
            '-framerate', str(fps),
            '-i', frames_out,
            '-i', src,                  # for audio
            '-map', '0:v', '-map', '1:a?',
            '-c:v', 'prores_ks',
            '-profile:v', '4444',
            '-pix_fmt', 'yuva444p12le',
            # Tag color metadata — same as v1 ProRes preset
            '-vf', 'colorspace=all=bt2020nc:range=tv',
            '-color_primaries', 'bt2020',
            '-color_trc', 'arib-std-b67',
            '-colorspace', 'bt2020nc',
            '-c:a', 'copy',
            out_path,
        ], check=True, capture_output=True)

    print(f'[ml_enhance] done → {out_path}', flush=True)
    return out_path


# ─── Quick test ───────────────────────────────────────────────────────────────

if __name__ == '__main__':
    import sys
    if len(sys.argv) < 3:
        print('Usage: python ml_enhance.py <input.mp4> <output.mov>')
        sys.exit(1)

    def progress(done, total):
        pct = done / total * 100
        print(f'  frame {done}/{total}  ({pct:.0f}%)', end='\r', flush=True)

    ml_convert(sys.argv[1], sys.argv[2], progress_cb=progress)
    print('\nDone.')
