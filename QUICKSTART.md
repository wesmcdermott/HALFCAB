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
6. **Convert** — Original is instant; HDR Graded / EXR run frame-by-frame (~3–4 min for a short clip; shows `Frame 45/193`).

---

## Which Mode?

| Mode | Use when… | Output |
|---|---|---|
| **Original** | Fast, predictable expand — no ML | Rec.2020 ProRes (curve-lifted) |
| **HDR Graded** ✦ | Finished gradeable master, no banding — **best default for delivery** | Rec.2020 12-bit ProRes |
| **EXR · Rec.709** | Compositing in **After Effects** | Linear EXR sequence (Rec.709) |
| **EXR · ACEScg** | Grading/comp in **Nuke / DaVinci Resolve** (ACES) | Linear EXR sequence (AP1) |
| **EXR · ACES2065-1** | ACES **interchange / archival** | Linear EXR sequence (AP0) |

**Recommendations:**
- AI video → professional delivery: **HDR Graded · 1000 nits**
- VFX/compositing with real overbright: **EXR ACEScg · 1000 nits**

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
