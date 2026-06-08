import React from 'react'
import styles from './ModePanel.module.css'

const MODES = [
  { id: 'v1',           label: 'Original',      tag: 'CURVES',
    desc: 'FFmpeg curve tone-map. Fast, no ML. Expands existing values.' },
  { id: 'graded',       label: 'HDR Graded',    tag: 'ML ✦',
    desc: 'Neural HDR reconstruction → filmic shoulder. Clean gradeable master, no banding.' },
  { id: 'exr',          label: 'EXR · Rec.709', tag: 'LINEAR',
    desc: 'Scene-linear EXR sequence, Rec.709 primaries. After Effects 32bpc.' },
  { id: 'exr_acescg',   label: 'EXR · ACEScg',  tag: 'ACES',
    desc: 'Scene-linear EXR, AP1 working space. Nuke / Resolve ACES.' },
  { id: 'exr_aces2065', label: 'EXR · ACES2065-1', tag: 'ACES',
    desc: 'Scene-linear EXR, AP0 compliant container. Interchange / archival.' },
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
            <span className={`${styles.tag} ${m.id === 'graded' ? styles.tagMl : ''}`}>{m.tag}</span>
          </button>
        ))}
      </div>
      {active && <div className={styles.desc}>{active.desc}</div>}
    </div>
  )
}
