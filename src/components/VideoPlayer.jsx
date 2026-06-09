import React, { useRef, useState, useEffect } from 'react'
import styles from './VideoPlayer.module.css'

export default function VideoPlayer({ filePath, onSeek, api }) {
  const videoRef      = useRef()
  const [playing, setPlaying]   = useState(false)
  const [current, setCurrent]   = useState(0)
  const [duration, setDuration] = useState(0)
  const [muted, setMuted]       = useState(true)

  // Load new file
  useEffect(() => {
    const v = videoRef.current
    if (!v) return
    setPlaying(false); setCurrent(0)
    // Stream via the backend (http) rather than file:// — works in dev (UI on
    // http://localhost, where file:// is blocked by web security) and packaged.
    const base = api || 'http://localhost:7892'
    v.src = filePath ? `${base}/video?path=${encodeURIComponent(filePath)}` : ''
    if (filePath) v.load()
  }, [filePath, api])

  const onLoadedMetadata = () => setDuration(videoRef.current?.duration || 0)

  // Only update display time during playback — don't fire scope updates
  const onTimeUpdate = () => {
    if (!videoRef.current) return
    setCurrent(videoRef.current.currentTime)
  }

  // Fire scope update on pause and on end
  const onPause = () => {
    setPlaying(false)
    onSeek?.(videoRef.current?.currentTime || 0)
  }

  const onEnded = () => {
    setPlaying(false)
    // Seek 0.1s before end to avoid frame extraction failures at exact EOF
    const t = Math.max(0, (videoRef.current?.duration || 0) - 0.1)
    onSeek?.(t)
  }

  const togglePlay = () => {
    const v = videoRef.current
    if (!v || !filePath) return
    if (playing) v.pause()
    else v.play().catch(() => {})
    setPlaying(!playing)
  }

  // Manual scrub — pause video then seek, fire scope update on release
  const scrubStart = () => {
    if (videoRef.current && playing) {
      videoRef.current.pause()
      setPlaying(false)
    }
  }
  const scrubMove = (e) => {
    const t = Number(e.target.value)
    setCurrent(t)
    if (videoRef.current) videoRef.current.currentTime = t
  }
  const scrubEnd = (e) => {
    const t = Number(e.target.value)
    onSeek?.(t)
  }

  const skip = (secs) => {
    const v = videoRef.current
    if (!v) return
    const t = Math.max(0, Math.min(v.duration || 0, v.currentTime + secs))
    v.currentTime = t
    setCurrent(t)
    if (!playing) onSeek?.(t)
  }

  const toggleMute = () => {
    if (videoRef.current) videoRef.current.muted = !muted
    setMuted(m => !m)
  }

  return (
    <div className={styles.player}>
      <div className={styles.videoWrap}>
        {filePath
          ? <video ref={videoRef} className={styles.video}
              onLoadedMetadata={onLoadedMetadata}
              onTimeUpdate={onTimeUpdate}
              onPause={onPause}
              onEnded={onEnded}
              muted={muted}
              playsInline
            />
          : <div className={styles.empty}>No file selected</div>
        }
      </div>

      <div className={styles.controls}>
        <button className={styles.ctrl} onClick={() => skip(-5)} title="−5s">⏮</button>
        <button className={`${styles.ctrl} ${styles.playBtn}`} onClick={togglePlay}>
          {playing ? '⏸' : '▶'}
        </button>
        <button className={styles.ctrl} onClick={() => skip(5)} title="+5s">⏭</button>

        <span className={styles.time}>{fmt(current)}</span>

        <input type="range" className={styles.scrub}
          min={0} max={duration || 0} step={0.04}
          value={current}
          onChange={scrubMove}
          onMouseDown={scrubStart}
          onMouseUp={scrubEnd}
        />

        <span className={styles.time}>{fmt(duration)}</span>
        <button className={`${styles.ctrl} ${muted ? styles.mutedBtn : ''}`} onClick={toggleMute} title={muted ? 'Unmute' : 'Mute'}>
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none" xmlns="http://www.w3.org/2000/svg">
            <polygon points="1,4.5 5,4.5 8,2 8,12 5,9.5 1,9.5" fill="currentColor"/>
            {muted
              ? <line x1="10" y1="4.5" x2="13.5" y2="9.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
              : <path d="M10 4.5 Q13 7 10 9.5" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round"/>
            }
          </svg>
        </button>
      </div>
    </div>
  )
}

function fmt(s) {
  if (!s || isNaN(s)) return '0:00'
  return `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`
}
