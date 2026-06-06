# Halfcab

**SDR → HDR Color Space Converter for AI-Generated Video**

Halfcab converts AI-generated video (8-bit SDR) into professional HDR color spaces for film and broadcast delivery. Drop in a video, analyze it, pick a preset, convert.

---

## Why

AI video generators (Kling, Wan, Sora, Runway) output 8-bit SDR MP4. Professional pipelines require 10-bit or 12-bit with Rec.2020 color space and HLG/PQ transfer curve metadata.

Additionally — AI models are trained on real-world photography which contains colors that technically exceed the Rec.709 SDR gamut. When the model renders those colors into an 8-bit SDR container, they get clamped. Halfcab creates the container where those colors have legal space to live.

---

## Features

- **Drag-and-drop queue** — batch convert multiple files
- **Auto Analyze** — scans 8 frames, measures peak luma, suggests Safe / Balanced / Punchy tone settings
- **6 color space presets** — ProRes 4444 (editing), HDR10, HLG, P3-D65, DCI Cinema, ACES CCT
- **4 video scopes** — Waveform (RGB, HLG-scaled), Vectorscope, Histogram, CIE xy chromaticity
- **HDR indicator overlay** — shows near-clip / hot / clipping zones on the video frame
- **Before/After/Split view** — compare source vs processed SDR simulation
- **Reconvert** — change settings and re-run without re-importing

---

## Requirements

- macOS (Apple Silicon or Intel)
- [FFmpeg](https://ffmpeg.org/download.html) — `brew install ffmpeg`
- Python 3 — `brew install python3`
- Python packages — `pip3 install flask flask-cors numpy pillow`

---

## Install

Download `Halfcab-1.0.0-arm64.dmg` (M1/M2/M3) or `Halfcab-1.0.0.dmg` (Intel) from Releases.

**First launch:** macOS Gatekeeper will block the app because it's not code-signed.  
Right-click → Open → Open to bypass.

---

## Development

```bash
git clone https://github.com/wesmcdermott/HALFCAB
cd HALFCAB
npm install
pip3 install flask flask-cors numpy pillow
npm run dev
```

Vite dev server: `http://localhost:5175`  
Flask backend: `http://localhost:7892`

---

## Build

```bash
npm run dist:mac
# Output: release/Halfcab-1.0.0-arm64.dmg (M-series)
#         release/Halfcab-1.0.0.dmg (Intel)
```

---

## How It Works

**Conversion pipeline:**
1. **Tone lift** — Curves filter lifts only the top 25% of the tonal range. Shadows/midtones untouched. Creates highlight headroom.
2. **Gamut expansion** — FFmpeg `colorspace` remaps Rec.709 → Rec.2020 primaries
3. **Encode** — ProRes 4444 at 12-bit / H.265 at 10-bit with correct HDR metadata tags

**Scopes** are PIL/NumPy rendered (not FFmpeg filter-based) to avoid aspect ratio constraints and get full control over scale and labels. The waveform is HLG-scaled — SDR white sits at 768/1023 (75% HLG reference white), matching what Premiere Pro shows after bringing the ProRes into an HLG sequence.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Electron 33 + React 18 + Vite 6 |
| Backend | Python 3 + Flask |
| Color conversion | FFmpeg 8 |
| Scope rendering | PIL/Pillow + NumPy |

---

## Roadmap — v2.0

- [ ] ML-enhanced HDR reconstruction (GMNet / MLP-iTM integration)
- [ ] Per-region overbright painting
- [ ] Zone sliders (Specular / Highlight / Midtone / Shadow targets)
- [ ] Segment Anything integration for auto light source detection

---

## License

MIT
