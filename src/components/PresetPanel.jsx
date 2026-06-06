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

export default function PresetPanel({
  preset, onPreset,
  peakNits, onPeakNits,
  toneStrength, onToneStr,
  outputDir, onPickOutput
}) {
  return (
    <div className={styles.panel}>

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

      <div className={styles.section}>
        <div className={styles.sectionLabel}>OUTPUT FOLDER</div>
        <div className={styles.outputRow} onClick={onPickOutput}>
          <span className={styles.outputPath}>{outputDir || 'Same as source'}</span>
          <span className={styles.outputBrowse}>Browse</span>
        </div>
      </div>

    </div>
  )
}
