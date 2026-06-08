import React from 'react'
import styles from './PresetPanel.module.css'

const PRESETS = [
  { id: 'prores', label: 'ProRes 4444', sub: 'Rec.2020 · 12-bit · .mov',
    badge: 'EDITING', badgeColor: '#2a9d8f',
    compat: 'QuickTime · Premiere · FCP · Resolve — best for editing' },
  { id: 'hdr10',  label: 'HDR10',       sub: 'Rec.2020 · PQ · 10-bit · .mp4',
    badge: 'STREAMING', badgeColor: '#888',
    compat: 'Netflix · YouTube · HDR10 TVs — delivery only, not QuickTime' },
  { id: 'hlg',    label: 'HLG Broadcast', sub: 'Rec.2020 · HLG · 10-bit · .mp4',
    badge: 'BROADCAST', badgeColor: '#888',
    compat: 'Broadcast HDR · BBC · NHK · some QuickTime support' },
  { id: 'p3',     label: 'P3-D65',      sub: 'DCI P3 · PQ · 10-bit · .mp4',
    badge: 'STREAMING', badgeColor: '#888',
    compat: 'Apple TV+ · Disney+ · P3 HDR displays' },
  { id: 'dci',    label: 'DCI Cinema',  sub: 'P3-DCI · γ2.6 · 12-bit · .mov',
    badge: 'THEATER', badgeColor: '#888',
    compat: 'Digital cinema projection · DCI-compliant' },
  { id: 'aces',   label: 'ACES CCT',    sub: 'Linear · 16-bit · .mov',
    badge: 'GRADE', badgeColor: '#888',
    compat: 'Hand to colorist in DaVinci Resolve / Baselight' },
]

const NITS = [400, 1000, 2000, 4000]

// Short "what you get / where it goes" guidance per ML mode — fills the panel
// and tells you the next step.
const MODE_INFO = {
  graded: {
    out: 'Rec.2020 12-bit ProRes (.mov)',
    use: 'Drop into a Rec.2020 sequence in Premiere or Resolve. Cleanly exposed, gradeable, no banding.',
  },
  exr: {
    out: 'Linear EXR sequence · Rec.709',
    use: 'Import the sequence into After Effects with the comp set to 32 bpc. Overbright values preserved.',
  },
  exr_acescg: {
    out: 'Linear EXR sequence · ACEScg (AP1)',
    use: 'Import into a Nuke or DaVinci Resolve ACES project — it auto-reads the color space.',
  },
  exr_aces2065: {
    out: 'Linear EXR sequence · ACES2065-1 (AP0)',
    use: 'ACES interchange / archival master for moving between facilities.',
  },
}

export default function PresetPanel({
  preset, onPreset,
  peakNits, onPeakNits,
  toneStrength, onToneStr,
  outputDir, onPickOutput,
  mode = 'graded',
}) {
  const isV1   = mode === 'v1'
  const isEXR  = mode.startsWith('exr')
  // Peak Brightness affects v1 + HDR Graded (HDR headroom). EXR is scene-linear
  // so peak doesn't apply there.
  const showNits = !isEXR

  return (
    <div className={styles.panel}>

      {/* v1 only — the original curves preset + tone map. ML modes pick the
          color space via the Conversion Mode panel, so these are hidden. */}
      {isV1 && (
        <>
          <div className={styles.section}>
            <div className={styles.sectionLabel}>TARGET COLOR SPACE</div>
            <div className={styles.presets}>
              {PRESETS.map(p => (
                <div
                  key={p.id}
                  className={`${styles.preset} ${preset === p.id ? styles.selected : ''}`}
                  onClick={() => onPreset(p.id)}
                >
                  <div className={styles.presetTop}>
                    <span className={styles.presetLabel}>{p.label}</span>
                    <span className={styles.presetBadge} style={{ color: p.badgeColor, borderColor: p.badgeColor + '55' }}>
                      {p.badge}
                    </span>
                  </div>
                  <span className={styles.presetSub}>{p.sub}</span>
                  {preset === p.id && (
                    <span className={styles.presetCompat}>{p.compat}</span>
                  )}
                </div>
              ))}
            </div>
          </div>

          <div className={styles.section}>
            <div className={styles.sliderRow}>
              <span className={styles.sectionLabel}>TONE MAP</span>
              <span className={styles.sliderVal}>{toneStrength}%</span>
            </div>
            <input
              type="range" min={0} max={100} value={toneStrength}
              onChange={e => onToneStr(Number(e.target.value))}
              className={styles.slider}
            />
            <div className={styles.sliderHints}>
              <span>Gentle</span><span>Aggressive</span>
            </div>
          </div>
        </>
      )}

      {showNits && (
        <div className={styles.section}>
          <div className={styles.sectionLabel}>PEAK BRIGHTNESS</div>
          <div className={styles.nitsRow}>
            {NITS.map(n => (
              <button
                key={n}
                className={`${styles.nitsBtn} ${peakNits === n ? styles.nitsActive : ''}`}
                onClick={() => onPeakNits(n)}
              >
                {n >= 1000 ? `${n/1000}k` : n}
              </button>
            ))}
            <span className={styles.nitsUnit}>nits</span>
          </div>
        </div>
      )}

      <div className={styles.section}>
        <div className={styles.sectionLabel}>OUTPUT FOLDER</div>
        <div className={styles.outputRow} onClick={onPickOutput}>
          <span className={styles.outputPath}>{outputDir || 'Same as source'}</span>
          <span className={styles.outputBrowse}>Browse</span>
        </div>
      </div>

      {/* Guidance card for ML modes — fills the panel + explains the output */}
      {!isV1 && MODE_INFO[mode] && (
        <div className={styles.section}>
          <div className={styles.sectionLabel}>OUTPUT</div>
          <div className={styles.infoOut}>{MODE_INFO[mode].out}</div>
          <div className={styles.infoUse}>{MODE_INFO[mode].use}</div>
        </div>
      )}

      <div className={styles.spacer} />

    </div>
  )
}
