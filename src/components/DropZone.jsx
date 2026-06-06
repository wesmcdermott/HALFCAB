import React, { useRef, useState } from 'react'
import styles from './DropZone.module.css'

export default function DropZone({ onDrop, onBrowse, hasFiles }) {
  const [dragging, setDragging] = useState(false)
  const ref = useRef()

  const handleDragOver = (e) => { e.preventDefault(); setDragging(true) }
  const handleDragLeave = () => setDragging(false)
  const handleDrop = (e) => {
    e.preventDefault()
    setDragging(false)
    const paths = Array.from(e.dataTransfer.files).map(f => f.path).filter(Boolean)
    if (paths.length) onDrop(paths)
  }

  if (hasFiles) return null

  return (
    <div
      ref={ref}
      className={`${styles.zone} ${dragging ? styles.dragging : ''}`}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      onClick={onBrowse}
    >
      <div className={styles.icon}>▣</div>
      <div className={styles.label}>Drop videos here</div>
      <div className={styles.sub}>mp4 · mov · mkv · mxf</div>
    </div>
  )
}
