import React from 'react'
import styles from './ConvertButton.module.css'

const MODE_VERB = {
  v1:           'Convert',
  graded:       'HDR Convert',
  exr:          'Export EXR',
  exr_acescg:   'Export ACEScg',
  exr_aces2065: 'Export ACES2065',
}

export default function ConvertButton({
  onClick, onReset, converting, count, doneCount, mode, mlProgress
}) {
  const disabled = converting || count === 0
  const isML = mode !== 'v1'
  const verb = MODE_VERB[mode] || 'Convert'

  return (
    <div className={styles.wrap}>
      <button
        className={`${styles.btn} ${converting ? styles.active : ''} ${isML ? styles.mlBtn : ''}`}
        onClick={onClick}
        disabled={disabled}
      >
        {converting
          ? <><span className={styles.spinner}>◌</span> {isML ? (mlProgress || 'Processing…') : 'Converting…'}</>
          : `${verb} ${count > 0 ? count : ''} File${count !== 1 ? 's' : ''}`
        }
      </button>
      {doneCount > 0 && !converting && (
        <button className={styles.resetBtn} onClick={onReset}>↺ Reconvert</button>
      )}
    </div>
  )
}
