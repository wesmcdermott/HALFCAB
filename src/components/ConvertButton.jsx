import React from 'react'
import styles from './ConvertButton.module.css'

export default function ConvertButton({ onClick, onReset, converting, count, doneCount }) {
  const disabled = converting || count === 0
  return (
    <div className={styles.wrap}>
      <button
        className={`${styles.btn} ${converting ? styles.active : ''}`}
        onClick={onClick}
        disabled={disabled}
      >
        {converting
          ? <><span className={styles.spinner}>◌</span> Converting…</>
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
