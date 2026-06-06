import React from 'react'
import styles from './FileQueue.module.css'

const STATUS_ICON = { idle: '○', converting: '◌', done: '●', error: '✕' }
const STATUS_COLOR = { idle: 'var(--text-dimmer)', converting: 'var(--accent)', done: 'var(--success)', error: 'var(--danger)' }

export default function FileQueue({ files, activeFile, onSelect, onRemove }) {
  if (!files.length) return null

  return (
    <div className={styles.queue}>
      <div className={styles.header}>
        <span>QUEUE</span>
        <span className={styles.count}>{files.length} file{files.length !== 1 ? 's' : ''}</span>
      </div>
      <div className={styles.list}>
        {files.map(f => (
          <div
            key={f.path}
            className={`${styles.row} ${f.path === activeFile ? styles.active : ''}`}
            onClick={() => onSelect(f.path)}
          >
            <span className={styles.status} style={{ color: STATUS_COLOR[f.status] }}>
              {f.status === 'converting'
                ? <span className={styles.spinner}>◌</span>
                : STATUS_ICON[f.status]}
            </span>
            <span className={styles.name} title={f.path}>{f.name}</span>
            {f.status === 'done' && (
              <button className={styles.reveal} onClick={e => { e.stopPropagation(); window.electronAPI?.revealFile(f.output) }} title="Show in Finder">↗</button>
            )}
            <button className={styles.remove} onClick={e => { e.stopPropagation(); onRemove(f.path) }}>×</button>
          </div>
        ))}
      </div>
    </div>
  )
}
