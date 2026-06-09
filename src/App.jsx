import React, { useState, useCallback } from 'react'
import Titlebar from './components/Titlebar.jsx'
import DropZone from './components/DropZone.jsx'
import FileQueue from './components/FileQueue.jsx'
import ModePanel from './components/ModePanel.jsx'
import PresetPanel from './components/PresetPanel.jsx'
import AnalyzePanel from './components/AnalyzePanel.jsx'
import ScopesPanel from './components/ScopesPanel.jsx'
import ConvertButton from './components/ConvertButton.jsx'
import styles from './styles/App.module.css'

const API = 'http://localhost:7892'

export default function App() {
  const [files, setFiles]           = useState([])
  const [preset, setPreset]         = useState('prores')
  const [peakNits, setPeakNits]     = useState(1000)
  const [toneStrength, setToneStr]  = useState(85)
  const [outputDir, setOutputDir]   = useState('')
  const [converting, setConverting] = useState(false)
  // Conversion mode: 'v1' | 'graded' | 'exr' | 'exr_acescg' | 'exr_aces2065'
  const [mode, setMode]             = useState('graded')
  const [activeFile, setActiveFile] = useState(null)   // file path for scopes preview
  const [scopeMode, setScopeMode]   = useState('waveform')

  const addFiles = useCallback((paths) => {
    const newFiles = paths
      .filter(p => !files.find(f => f.path === p))
      .map(p => ({ path: p, name: p.split('/').pop(), status: 'idle', output: null }))
    setFiles(prev => [...prev, ...newFiles])
    if (!activeFile && newFiles.length) setActiveFile(newFiles[0].path)
  }, [files, activeFile])

  const removeFile = (path) => {
    setFiles(prev => prev.filter(f => f.path !== path))
    if (activeFile === path) setActiveFile(null)
  }

  const pickFiles = async () => {
    if (!window.electronAPI) return
    const paths = await window.electronAPI.openFileDialog()
    if (paths?.length) addFiles(paths)
  }

  const pickOutput = async () => {
    if (!window.electronAPI) return
    const dir = await window.electronAPI.openFolderDialog()
    if (dir) setOutputDir(dir)
  }

  const setFile = (path, patch) =>
    setFiles(prev => prev.map(f => f.path === path ? { ...f, ...patch } : f))

  // v1: fast FFmpeg curves tone-map (no ML). Synchronous /convert.
  const runV1 = async (file) => {
    const data = await fetch(`${API}/convert`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        input: file.path, preset, peak_nits: peakNits,
        tone_strength: toneStrength / 100, output_dir: outputDir || null,
      })
    }).then(r => r.json())
    if (!data.ok) throw new Error(data.error)
    return data.output
  }

  // v2: ML gain-map (graded / exr / exr_acescg / exr_aces2065). Async + polling.
  const runML = async (file, outputFormat) => {
    const res = await fetch(`${API}/ml-convert`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        input: file.path, peak_nits: peakNits,
        output_format: outputFormat, output_dir: outputDir || null,
      })
    }).then(r => r.json())
    if (!res.ok) throw new Error(res.error)
    return await new Promise((resolve, reject) => {
      const poll = setInterval(async () => {
        const p = await fetch(`${API}/ml-progress/${res.job_id}`).then(r => r.json())
        setFile(file.path, { mlProgress: p.total > 0 ? `Frame ${p.done}/${p.total}` : p.status })
        if (p.status === 'done')  { clearInterval(poll); resolve(p.output) }
        if (p.status === 'error') { clearInterval(poll); reject(new Error(p.error)) }
      }, 800)
    })
  }

  const convertAll = async () => {
    const pending = files.filter(f => f.status === 'idle' || f.status === 'error')
    if (!pending.length) return
    setConverting(true)
    for (const file of pending) {
      setFile(file.path, { status: 'converting', progress: 0, mlProgress: mode === 'v1' ? null : 'Starting…' })
      try {
        const output = mode === 'v1' ? await runV1(file) : await runML(file, mode)
        setFile(file.path, { status: 'done', output, progress: 100 })
      } catch (e) {
        setFile(file.path, { status: 'error', error: String(e.message).slice(0, 200) })
      }
    }
    setConverting(false)
  }

  const resetDone = () =>
    setFiles(prev => prev.map(f => f.status === 'done' ? { ...f, status: 'idle', output: null } : f))

  return (
    <div className={styles.root}>
      <div className="titlebar-drag" />
      <Titlebar />

      <div className={styles.body}>
        {/* LEFT — queue + controls */}
        <div className={styles.left}>
          <DropZone onDrop={addFiles} onBrowse={pickFiles} hasFiles={files.length > 0} />
          <FileQueue
            files={files}
            activeFile={activeFile}
            onSelect={setActiveFile}
            onRemove={removeFile}
          />
          <ModePanel mode={mode} onMode={setMode} />
          <PresetPanel
            preset={preset}           onPreset={setPreset}
            peakNits={peakNits}       onPeakNits={setPeakNits}
            toneStrength={toneStrength} onToneStr={setToneStr}
            outputDir={outputDir}     onPickOutput={pickOutput}
            mode={mode}
          />
          <AnalyzePanel
            filePath={activeFile}
            onApply={({ tone_strength, peak_nits }) => {
              setToneStr(Math.round(tone_strength * 100))
              setPeakNits(peak_nits)
            }}
          />
          <ConvertButton
            onClick={convertAll}
            converting={converting}
            count={files.filter(f => f.status === 'idle' || f.status === 'error').length}
            doneCount={files.filter(f => f.status === 'done').length}
            onReset={resetDone}
            mode={mode}
            mlProgress={files.find(f => f.status === 'converting')?.mlProgress}
          />
        </div>

        {/* RIGHT — scopes */}
        <div className={styles.right}>
          <ScopesPanel
            filePath={activeFile}
            scopeMode={scopeMode}
            onScopeMode={setScopeMode}
            api={API}
            settings={{ mode, preset, peak_nits: peakNits, tone_strength: toneStrength / 100 }}
          />
        </div>
      </div>
    </div>
  )
}
