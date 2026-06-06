import React, { useState, useEffect, useRef, useCallback } from 'react'
import styles from './ScopesPanel.module.css'
import VideoPlayer from './VideoPlayer.jsx'

const SCOPE_TABS = [
  { id: 'waveform',    label: 'Waveform' },
  { id: 'vectorscope', label: 'Vector' },
  { id: 'histogram',   label: 'Histogram' },
  { id: 'cie',         label: 'CIE xy' },
  { id: 'all',         label: 'All 4' },
]

export default function ScopesPanel({ filePath, scopeMode, onScopeMode, api, settings }) {
  const [scopeData, setScopeData]     = useState({})
  const [sourceFrame, setSourceFrame] = useState(null)
  const [processedFrame, setProcessed] = useState(null)
  const [overlayImg, setOverlayImg]   = useState(null)
  const [overlayStats, setOStats]     = useState(null)
  const [showOverlay, setShowOverlay] = useState(true)
  const [viewMode, setViewMode]       = useState('before') // 'before' | 'after' | 'split'
  const [loadingScopes, setLoadingScopes] = useState(false)
  const [loadingPreview, setLoadingPreview] = useState(false)
  const [frameTime, setFrameTime]     = useState(0)
  const [duration, setDuration]       = useState(0)
  const [peakInfo, setPeakInfo]       = useState(null)
  const scrubTimer      = useRef()
  const previewTimer    = useRef()
  const lastSettings    = useRef(null)
  const sourceAbort     = useRef(null)   // AbortController for in-flight scope fetch
  const previewAbort    = useRef(null)   // AbortController for in-flight preview fetch

  // Fetch scopes + source frame — cancels any previous in-flight request
  const fetchSource = useCallback(async (path, t, s) => {
    if (!path) return
    // Cancel previous request
    sourceAbort.current?.abort()
    sourceAbort.current = new AbortController()
    const signal = sourceAbort.current.signal

    setLoadingScopes(true)
    const scopeBody = { path, time: t, ...(s || {}) }
    try {
      const [scopeRes, frameRes] = await Promise.all([
        fetch(`${api}/scopes`, { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(scopeBody), signal }).then(r=>r.json()),
        fetch(`${api}/frame`,  { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ path, time: t }), signal }).then(r=>r.json()),
      ])
      if (scopeRes?.ok) {
        if (Object.keys(scopeRes.scopes||{}).length > 0)
          setScopeData(prev => ({ ...prev, ...scopeRes.scopes }))
        if (scopeRes.duration) setDuration(scopeRes.duration)
        if (scopeRes.peak_info) setPeakInfo(scopeRes.peak_info)
      }
      if (frameRes?.ok && frameRes.frame) setSourceFrame(frameRes.frame)
    } catch (e) {
      if (e.name !== 'AbortError') console.error('scope fetch error', e)
    }
    setLoadingScopes(false)
  }, [api])

  // Fetch processed preview — cancels any previous in-flight request
  const fetchPreview = useCallback(async (path, t, s) => {
    if (!path) return
    previewAbort.current?.abort()
    previewAbort.current = new AbortController()
    const signal = previewAbort.current.signal

    setLoadingPreview(true)
    try {
      const res = await fetch(`${api}/preview-frame`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path, time: t, ...s }),
        signal,
      }).then(r=>r.json())
      if (res?.ok) {
        setProcessed(res.frame)
        setOverlayImg(res.overlay)
        setOStats(res.stats)
      }
    } catch (e) {
      if (e.name !== 'AbortError') console.error('preview fetch error', e)
    }
    setLoadingPreview(false)
  }, [api])

  // When file changes — reset and load everything
  useEffect(() => {
    if (filePath) {
      setFrameTime(0)
      setProcessed(null); setOverlayImg(null); setOStats(null)
      fetchSource(filePath, 0, settings)
      if (settings) fetchPreview(filePath, 0, settings)
    } else {
      setScopeData({}); setSourceFrame(null); setProcessed(null)
      setPeakInfo(null); setOStats(null)
    }
  }, [filePath])

  // When settings change — debounce both scopes and preview
  useEffect(() => {
    if (!filePath || !settings) return
    const key = JSON.stringify(settings)
    if (key === lastSettings.current) return
    lastSettings.current = key
    clearTimeout(previewTimer.current)
    previewTimer.current = setTimeout(() => {
      fetchSource(filePath, frameTime, settings)
      fetchPreview(filePath, frameTime, settings)
    }, 400)
  }, [settings, filePath])

  // Called by VideoPlayer when playback position changes
  const scrub = (t) => {
    setFrameTime(t)
    clearTimeout(scrubTimer.current)
    scrubTimer.current = setTimeout(() => {
      fetchSource(filePath, t, settings)
      fetchPreview(filePath, t, settings)
    }, 500)  // longer debounce — video is playing
  }

  const activeFrame = viewMode === 'before' ? sourceFrame : processedFrame

  const renderScopeBox = (id, label) => (
    <div className={styles.scopeBox} key={id}>
      <div className={styles.scopeLabel}>
        {label}
        {loadingScopes && <span className={styles.scopeLabelSpin}> ⟳</span>}
      </div>
      {scopeData[id]
        ? <img className={styles.scopeImg} src={`data:image/png;base64,${scopeData[id]}`} alt={label} />
        : <div className={styles.scopeEmpty}>{loadingScopes ? '⟳' : filePath ? '…' : '—'}</div>
      }
    </div>
  )

  const visibleScopes = scopeMode === 'all'
    ? SCOPE_TABS.filter(m => m.id !== 'all')
    : SCOPE_TABS.filter(m => m.id === scopeMode)

  return (
    <div className={styles.panel}>

      {/* ── Top bar: scope tabs + peak ── */}
      <div className={styles.topBar}>
        <div className={styles.tabs}>
          {SCOPE_TABS.map(m => (
            <button key={m.id}
              className={`${styles.tab} ${scopeMode === m.id ? styles.tabActive : ''}`}
              onClick={() => onScopeMode(m.id)}
            >{m.label}</button>
          ))}
        </div>
        <div className={styles.topRight}>
          {peakInfo && (
            <div className={styles.peakBadge}>
              <span className={styles.peakLabel}>SRC PEAK</span>
              <span className={styles.peakVal} style={{ color: peakInfo.clipping ? 'var(--danger)' : 'var(--accent)' }}>
                {(peakInfo.max * 100).toFixed(1)}%
              </span>
            </div>
          )}
          {loadingScopes && <span className={styles.loadSpin}>⟳</span>}
        </div>
      </div>

      {/* ── Scopes area ── */}
      {filePath ? (
        <div className={`${styles.scopes} ${scopeMode === 'all' ? styles.grid2x2 : styles.single}`}>
          {visibleScopes.map(m => renderScopeBox(m.id, m.label))}
        </div>
      ) : (
        <div className={styles.emptyState}>
          <div className={styles.emptyIcon}>◈</div>
          <div className={styles.emptyText}>Select a file from the queue to analyze</div>
        </div>
      )}

      {/* ── Video preview ── */}
      {filePath && (
        <div className={styles.videoSection}>

          {/* Toolbar: Source/Processed/Split + HDR stats + overlay toggle */}
          <div className={styles.videoBar}>
            <div className={styles.viewToggle}>
              {[['before','Source'],['after','Processed'],['split','Split']].map(([v,label]) => (
                <button key={v}
                  className={`${styles.viewBtn} ${viewMode===v ? styles.viewActive : ''}`}
                  onClick={() => setViewMode(v)}
                >{label}</button>
              ))}
              {loadingPreview && <span className={styles.loadSpin} style={{marginLeft:6}}>⟳</span>}
            </div>

            {overlayStats && viewMode !== 'before' && (
              <div className={styles.hdrStats}>
                <span className={styles.statItem} style={{color:'#ffdc00'}}>▪ {overlayStats.pct_above_1?.toFixed(1)}% &gt;1.0</span>
                <span className={styles.statItem} style={{color:'#ff6400'}}>▪ {overlayStats.pct_above_1_5?.toFixed(1)}% &gt;1.5</span>
                <span className={styles.statItem} style={{color:'#ff4444'}}>▪ {overlayStats.pct_above_3?.toFixed(1)}% &gt;3.0</span>
                <span className={styles.statPeak}>peak ×{overlayStats.scale}</span>
              </div>
            )}

            {viewMode !== 'before' && (
              <button
                className={`${styles.overlayBtn} ${showOverlay ? styles.overlayOn : ''}`}
                onClick={() => setShowOverlay(v => !v)}
              >HDR Map {showOverlay ? 'ON' : 'OFF'}</button>
            )}
          </div>

          {/* Legend strip */}
          {viewMode !== 'before' && showOverlay && (
            <div className={styles.legend}>
              <span className={styles.legendItem}><span className={styles.dot} style={{background:'#ffdc00'}}/>1.0–1.5×</span>
              <span className={styles.legendItem}><span className={styles.dot} style={{background:'#ff6400'}}/>1.5–3.0×</span>
              <span className={styles.legendItem}><span className={styles.dot} style={{background:'#ff2222'}}/>3.0×+</span>
              <span className={styles.statPeak} style={{marginLeft:4}}>HDR headroom zones</span>
            </div>
          )}

          {/* Video area */}
          {viewMode === 'split' ? (
            // Split: source video on left, processed still-frame on right
            <div className={styles.splitWrap}>
              <div className={styles.splitPane}>
                <div className={styles.splitLabel}>SOURCE</div>
                <VideoPlayer
                  filePath={filePath}
                  onSeek={scrub}
                  api={api}
                />
              </div>
              <div className={styles.splitDivider} />
              <div className={styles.splitPane}>
                <div className={styles.splitLabel}>
                  PROCESSED <span style={{color:'var(--accent-lo)',fontSize:9}}>SDR sim</span>
                </div>
                <div className={styles.frameWrap}>
                  {processedFrame
                    ? <img className={styles.videoFrame} src={`data:image/jpeg;base64,${processedFrame}`} alt="processed" />
                    : <div className={styles.videoEmpty}>{loadingPreview ? '⟳' : '—'}</div>}
                  {showOverlay && overlayImg &&
                    <img className={styles.overlayFrame} src={`data:image/png;base64,${overlayImg}`} alt="overlay" />}
                </div>
              </div>
            </div>
          ) : viewMode === 'after' ? (
            // Processed: still frame with overlay
            <div className={styles.frameWrap} style={{flex:1,minHeight:0}}>
              {processedFrame
                ? <img className={styles.videoFrame} src={`data:image/jpeg;base64,${processedFrame}`} alt="processed" />
                : <div className={styles.videoEmpty}>{loadingPreview ? '⟳ Rendering…' : '—'}</div>}
              {showOverlay && overlayImg &&
                <img className={styles.overlayFrame} src={`data:image/png;base64,${overlayImg}`} alt="overlay" />}
            </div>
          ) : (
            // Source: real video player
            <VideoPlayer
              filePath={filePath}
              onSeek={scrub}
              overlayImg={showOverlay ? overlayImg : null}
              showOverlay={false}
              api={api}
            />
          )}
        </div>
      )}
    </div>
  )
}
