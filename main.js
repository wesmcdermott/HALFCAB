const { app, BrowserWindow, ipcMain, dialog, shell } = require('electron')
const path = require('path')
const { spawn } = require('child_process')

const isDev = process.env.NODE_ENV === 'development'
let mainWindow
let backendProcess
let isQuitting = false

function startBackend() {
  const backendPath = isDev
    ? path.join(__dirname, 'backend', 'server.py')
    : path.join(process.resourcesPath, 'app.asar.unpacked', 'backend', 'server.py')

  backendProcess = spawn('python3', [backendPath], {
    env: { ...process.env, PYTHONUNBUFFERED: '1' }
  })
  backendProcess.stdout.on('data', d => console.log('[backend]', d.toString()))
  backendProcess.stderr.on('data', d => console.error('[backend]', d.toString()))

  // Don't treat backend exit as a crash if we're already quitting
  backendProcess.on('exit', (code) => {
    if (!isQuitting) console.warn('[backend] exited unexpectedly with code', code)
  })
}

function killBackend() {
  if (!backendProcess) return
  const proc = backendProcess          // keep a local ref so the timeout works
  backendProcess = null
  try {
    proc.kill('SIGTERM')               // server.py handles this → clean exit(0)
    // Fallback force-kill if it didn't exit (uses the captured ref, not the
    // now-nulled global — the previous bug meant SIGKILL never actually fired)
    setTimeout(() => { try { proc.kill('SIGKILL') } catch (_) {} }, 800)
  } catch (_) {}
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 800,
    minWidth: 1024,
    minHeight: 680,
    titleBarStyle: 'hiddenInset',
    backgroundColor: '#0a0a0a',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      webSecurity: false,
    }
  })
  if (isDev) {
    mainWindow.loadURL('http://localhost:5175')
  } else {
    mainWindow.loadFile(path.join(__dirname, 'dist', 'index.html'))
  }
}

app.whenReady().then(() => {
  startBackend()
  setTimeout(createWindow, 900)
})

// Handle ⌘Q and File > Quit — this fires before windows close
app.on('before-quit', () => {
  isQuitting = true
  killBackend()
})

// macOS: closing all windows doesn't quit the app
app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    isQuitting = true
    killBackend()
    app.quit()
  }
})

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) createWindow()
})

// Handle forced termination signals cleanly
process.on('SIGTERM', () => { isQuitting = true; killBackend(); process.exit(0) })
process.on('SIGINT',  () => { isQuitting = true; killBackend(); process.exit(0) })

ipcMain.handle('open-file-dialog', async () => {
  const { filePaths } = await dialog.showOpenDialog(mainWindow, {
    properties: ['openFile', 'multiSelections'],
    filters: [{ name: 'Video', extensions: ['mp4', 'mov', 'mkv', 'avi', 'webm', 'mxf'] }]
  })
  return filePaths
})

ipcMain.handle('open-folder-dialog', async () => {
  const { filePaths } = await dialog.showOpenDialog(mainWindow, {
    properties: ['openDirectory']
  })
  return filePaths[0] || null
})

ipcMain.handle('reveal-file', (_, p) => shell.showItemInFolder(p))
