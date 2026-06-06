import React from 'react'
import styles from './Titlebar.module.css'

export default function Titlebar() {
  return (
    <div className={styles.bar}>
      <div className={styles.logo}>
        <span className={styles.logoText}>HALFCAB</span>
      </div>
      <div className={styles.sub}>SDR → HDR Color Space Converter</div>
    </div>
  )
}
