import React, { useState, useCallback } from 'react'
import Titlebar from './components/Titlebar.jsx'
import DropZone from './components/DropZone.jsx'
import FileQueue from './components/FileQueue.jsx'
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

  const convertAll = async () => {
    const pending = files.filter(f => f.status === 'idle' || f.status === 'error')
    if (!pending.length) return
    setConverting(true)

    for (const file of pending) {
      setFiles(prev => prev.map(f => f.path === file.path ? { ...f, status: 'converting', progress: 0 } : f))
      try {
        const res = await fetch(`${API}/convert`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            input: file.path,
            preset,
            peak_nits: peakNits,
            tone_strength: toneStrength / 100,
            output_dir: outputDir || null,
          })
        })
        const data = await res.json()
        if (data.ok) {
          setFiles(prev => prev.map(f => f.path === file.path ? { ...f, status: 'done', output: data.output, progress: 100 } : f))
        } else {
          setFiles(prev => prev.map(f => f.path === file.path ? { ...f, status: 'error', error: data.error } : f))
        }
      } catch (e) {
        setFiles(prev => prev.map(f => f.path === file.path ? { ...f, status: 'error', error: e.message } : f))
      }
    }
    setConverting(false)
  }

  const resetDone = () => {
    setFiles(prev => prev.map(f => f.status === 'done' ? { ...f, status: 'idle', output: null } : f))
  }

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
          <PresetPanel
            preset={preset}           onPreset={setPreset}
            peakNits={peakNits}       onPeakNits={setPeakNits}
            toneStrength={toneStrength} onToneStr={setToneStr}
            outputDir={outputDir}     onPickOutput={pickOutput}
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
          />
        </div>

        {/* RIGHT — scopes */}
        <div className={styles.right}>
          <ScopesPanel
            filePath={activeFile}
            scopeMode={scopeMode}
            onScopeMode={setScopeMode}
            api={API}
            settings={{ preset, peak_nits: peakNits, tone_strength: toneStrength / 100 }}
          />
        </div>
      </div>
    </div>
  )
}
