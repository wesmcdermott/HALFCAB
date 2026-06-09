# Halfcab — Quickstart

Convert AI-generated video (8-bit SDR) into professional HDR / wide-gamut deliverables.

> **Requires** FFmpeg and Python 3 installed on the machine. Open Halfcab from
> Applications — the backend starts automatically.
> First launch only: right-click the app → **Open** → **Open** (it's unsigned).

---

## 6 Steps

1. **Load** — drag a clip onto the drop zone (or click to browse). Click it in the queue to select.
2. **Analyze** (optional) — click **⬡ Analyze Video**. It scans 8 frames and reports content type, peak brightness, and suggested settings.
3. **Pick a mode** (see table below).
4. **Peak Brightness** — use **1000 nits** for most delivery. (4000 only for high-end HDR mastering.)
5. **Output folder** (optional) — Browse to choose; defaults next to the source.
6. **Convert** — Curve Expand is instant; HDR Graded / EXR run frame-by-frame (~3–4 min for a short clip; shows `Frame 45/193`).

---

## Which Mode?

| Mode | Use when… | Output |
|---|---|---|
| **Curve Expand** | Fast, predictable expand — no ML | Rec.2020 ProRes (curve-lifted) |
| **HDR Graded** ✦ | Finished gradeable master, no banding — **best default for delivery** | Rec.2020 12-bit ProRes |
| **EXR · Rec.709** | Compositing in **After Effects** | Linear EXR sequence (Rec.709) |
| **EXR · ACEScg** | Grading/comp in **Nuke / DaVinci Resolve** (ACES) | Linear EXR sequence (AP1) |
| **EXR · ACES2065-1** | ACES **interchange / archival** | Linear EXR sequence (AP0) |

**Recommendations:**
- AI video → professional delivery: **HDR Graded · 1000 nits**
- VFX/compositing with real overbright: **EXR ACEScg · 1000 nits**

---

## Conversion Modes Explained

### Curve Expand
The original FFmpeg curve-based conversion — the one mode that does **not** use
ML. It applies a fixed tone curve to stretch your existing 8-bit values into a
wider 10/12-bit container and target color space (driven by the preset + Tone
Map slider). It does **not** reconstruct or recover any detail; it just remaps
the values that are already there, so blown-out areas stay blown out, just
rescaled. Fast, no GPU, fully deterministic. Use it for a quick test or when you
want a predictable mathematical curve with no ML interpretation. It's the only
mode with a `CURVES` badge instead of `ML`.

### HDR Graded + the EXR modes (all ML)
These four share one engine: the **GMNet machine-learning gain-map
reconstruction**. The model looks at each frame and predicts a per-pixel gain
map, recovering the highlight/specular energy the 8-bit source clipped (a flat
blown-out lamp gets pushed back to ~2.5× brightness). That produces a
scene-linear HDR image with genuine overbright values above 1.0. They differ
only in what they output:

**HDR Graded (ProRes)** — the *finished master* path. Rolls the reconstructed
HDR into a 10/12-bit video container: Rec.709→Rec.2020 gamut, a filmic highlight
shoulder (highlights land ~90% with headroom above), the bt709 transfer it's
tagged with, and 12-bit dither for no banding. Output is a clean, gradeable
**Rec.2020 ProRes 4444 .mov**. Because it's *video*, it can't store values above
1.0 — the HDR lives in the **curve**, not in overbright pixels. Best default for
editing, grading, and delivery.

**EXR modes** — the *VFX/comp* path. All three write scene-linear OpenEXR
sequences that **preserve the genuine overbright (>1.0) values**, differing only
in color space:
- **EXR · Rec.709** — Rec.709 primaries, for After Effects 32bpc compositing.
- **EXR · ACEScg (AP1)** — ACES working space, for Nuke / Resolve ACES.
- **EXR · ACES2065-1 (AP0)** — ACES interchange/archival container.

Use an EXR mode any time you need true overbright energy in a compositor or an
ACES pipeline.

**One-line distinction:**
- **Curve Expand** = remap existing values (no ML)
- **HDR Graded** = ML reconstruction → finished video master (HDR in the *curve*)
- **EXR** = ML reconstruction → scene-linear file with real overbright (HDR in the *values*)

---

## Where the Output Goes

| Output | Next step |
|---|---|
| **HDR Graded .mov** | Drop into a **Rec.2020** sequence (Premiere/Resolve). Not an HLG sequence — that remaps the white point. |
| **EXR Rec.709** | Import as a sequence in After Effects; set the comp to **32 bpc**. |
| **EXR ACEScg / ACES2065-1** | Import into a Nuke / Resolve **ACES** project — it auto-reads the color space. |

---

## Reading the Scopes (right panel)

- **Waveform** — brightness bottom→top, frame left→right. Green **768** line = SDR reference white; above it = HDR headroom; red line = clip.
- **Histogram** — per-channel levels; red banner warns of clipping.
- **Vectorscope** — saturation (center = neutral, edges = saturated).
- **CIE xy** — your colors vs the Rec.709 / P3 / Rec.2020 gamut triangles.

Use the player to scrub — scopes update to the frame you stop on.

---

## Notes

- EXR output is **genuine scene-linear** (no baked gamma) with overbright values >1.0 preserved — view it in a 32-bit/linear-aware app (Photoshop, AE 32bpc, Nuke, Resolve).
- A 10/12-bit **video** file (ProRes) can't hold values >1.0 — its HDR lives in the color curve. Only the **EXR** modes carry true overbright. For overbright energy in compositing, use EXR.
