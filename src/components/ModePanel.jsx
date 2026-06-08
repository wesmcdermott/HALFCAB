import React from 'react'
import styles from './ModePanel.module.css'

// Every mode except Original uses the GMNet ML gain-map reconstruction;
// they differ only in the output format/color space (shown in `fmt`).
const MODES = [
  { id: 'v1',           label: 'Original',         ml: false, fmt: 'CURVES',
    desc: 'FFmpeg curve tone-map. Fast, no ML — expands existing values.' },
  { id: 'graded',       label: 'HDR Graded',       ml: true,  fmt: 'ProRes',
    desc: 'ML HDR reconstruction → filmic shoulder. Clean gradeable Rec.2020 master, no banding.' },
  { id: 'exr',          label: 'EXR · Rec.709',    ml: true,  fmt: 'EXR',
    desc: 'ML reconstruction → scene-linear EXR, Rec.709 primaries. After Effects 32bpc.' },
  { id: 'exr_acescg',   label: 'EXR · ACEScg',     ml: true,  fmt: 'EXR',
    desc: 'ML reconstruction → scene-linear EXR, ACEScg/AP1. Nuke / Resolve ACES.' },
  { id: 'exr_aces2065', label: 'EXR · ACES2065-1', ml: true,  fmt: 'EXR',
    desc: 'ML reconstruction → scene-linear EXR, ACES2065-1/AP0 container. Interchange / archival.' },
]

export default function ModePanel({ mode, onMode }) {
  const active = MODES.find(m => m.id === mode)
  return (
    <div className={styles.panel}>
      <div className={styles.label}>CONVERSION MODE</div>
      <div className={styles.list}>
        {MODES.map(m => (
          <button
            key={m.id}
            className={`${styles.mode} ${mode === m.id ? styles.active : ''}`}
            onClick={() => onMode(m.id)}
          >
            <span className={styles.modeLabel}>{m.label}</span>
            <span className={styles.tags}>
              {m.ml && <span className={`${styles.tag} ${styles.tagMl}`}>ML</span>}
              <span className={styles.tag}>{m.fmt}</span>
            </span>
          </button>
        ))}
      </div>
      {active && <div className={styles.desc}>{active.desc}</div>}
    </div>
  )
}
