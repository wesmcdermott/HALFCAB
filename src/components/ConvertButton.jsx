import React from 'react'
import styles from './ConvertButton.module.css'

export default function ConvertButton({
  onClick, onReset, converting, count, doneCount,
  mlMode, onMlMode, mlProgress
}) {
  const disabled = converting || count === 0

  return (
    <div className={styles.wrap}>

      {/* v1 / v2 mode toggle */}
      <div className={styles.modeRow}>
        <span className={styles.modeLabel}>MODE</span>
        <div className={styles.modeToggle}>
          <button
            className={`${styles.modeBtn} ${!mlMode ? styles.modeActive : ''}`}
            onClick={() => onMlMode(false)}
            disabled={converting}
          >
            v1 Curves
          </button>
          <button
            className={`${styles.modeBtn} ${mlMode ? styles.modeActive : ''}`}
            onClick={() => onMlMode(true)}
            disabled={converting}
          >
            v2 ML ✦
          </button>
        </div>
      </div>

      {/* Mode description */}
      <div className={styles.modeDesc}>
        {mlMode
          ? 'ITMLUT neural network — genuine per-pixel HDR reconstruction'
          : 'FFmpeg curves lift — fast, no dependencies'}
      </div>

      {/* Convert button */}
      <button
        className={`${styles.btn} ${converting ? styles.active : ''} ${mlMode ? styles.mlBtn : ''}`}
        onClick={onClick}
        disabled={disabled}
      >
        {converting
          ? mlMode
            ? <><span className={styles.spinner}>◌</span> {mlProgress || 'Processing…'}</>
            : <><span className={styles.spinner}>◌</span> Converting…</>
          : mlMode
            ? `ML Enhance ${count > 0 ? count : ''} File${count !== 1 ? 's' : ''}`
            : `Convert ${count > 0 ? count : ''} File${count !== 1 ? 's' : ''}`
        }
      </button>

      {doneCount > 0 && !converting && (
        <button className={styles.resetBtn} onClick={onReset}>
          ↺ Reconvert
        </button>
      )}
    </div>
  )
}
