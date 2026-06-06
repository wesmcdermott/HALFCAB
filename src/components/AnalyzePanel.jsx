import React, { useState } from 'react'
import styles from './AnalyzePanel.module.css'

const API = 'http://localhost:7892'

export default function AnalyzePanel({ filePath, onApply }) {
  const [result, setResult]   = useState(null)
  const [loading, setLoading] = useState(false)

  const analyze = async () => {
    if (!filePath) return
    setLoading(true); setResult(null)
    const res = await fetch(`${API}/analyze`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path: filePath })
    }).then(r => r.json()).catch(() => null)
    setResult(res)
    setLoading(false)
  }

  return (
    <div className={styles.panel}>
      <div className={styles.header}>
        <span className={styles.label}>AUTO ANALYZE</span>
        <button
          className={`${styles.btn} ${loading ? styles.scanning : ''}`}
          onClick={analyze}
          disabled={!filePath || loading}
        >
          {loading ? <><span className={styles.spin}>⟳</span> Scanning…</> : '⬡ Analyze Video'}
        </button>
      </div>

      {result?.ok && (
        <div className={styles.results}>
          {/* Content summary */}
          <div className={styles.summary}>
            <span className={styles.chip}>{result.content_type}</span>
            <span className={styles.stat}>Peak <b>{(result.worst_peak*100).toFixed(1)}%</b></span>
            <span className={styles.stat}>Mid <b>{(result.avg_mid*100).toFixed(1)}%</b></span>
            {result.hot_frames > 0 &&
              <span className={styles.statWarn}>{result.hot_frames} hot frame{result.hot_frames>1?'s':''}</span>}
          </div>

          {/* Warning */}
          {result.warning && (
            <div className={styles.warning}>{result.warning}</div>
          )}

          {/* Three suggestions */}
          <div className={styles.suggestions}>
            {Object.entries(result.suggestions).map(([key, s]) => (
              <div key={key} className={styles.suggestion}>
                <div className={styles.sugTop}>
                  <span className={styles.sugLabel}>{s.label}</span>
                  <span className={styles.sugStrength}>{Math.round(s.strength*100)}%</span>
                  <button
                    className={styles.applyBtn}
                    onClick={() => onApply({ tone_strength: s.strength, peak_nits: result.rec_nits })}
                  >Apply</button>
                </div>
                <span className={styles.sugDesc}>{s.desc}</span>
              </div>
            ))}
          </div>

          <div className={styles.recNits}>
            Suggested peak brightness: <b>{result.rec_nits} nits</b>
          </div>
        </div>
      )}

      {result && !result.ok && (
        <div className={styles.error}>{result.error}</div>
      )}
    </div>
  )
}
