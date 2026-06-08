const { app, BrowserWindow, ipcMain, dialog, shell } = require('electron')
const path = require('path')
const { spawn } = require('child_process')

// ── Crash/Stability switches (must be set before app is ready) ──────────────
// The real cause of the "Halfcab quit unexpectedly" dialog: a use-after-free
// in Electron's macOS accessibility tree (objc_msgSend on freed memory),
// triggered while running by the OS/assistive tools (e.g. screen recorders)
// querying the app's a11y attributes — confirmed by the crash report.
//   - disable-crashpad / disable-crash-reporter: stop the crash-handler
//     subprocess whose exit produces the macOS dialog.
//   - disable-gpu-sandbox / no-sandbox: avoid GPU/Metal process crashes
//     common with Electron + Metal on macOS.
// (Same mitigations used in the working Z-BOY app.)
app.commandLine.appendSwitch('disable-crashpad')
app.commandLine.appendSwitch('disable-crash-reporter')
app.commandLine.appendSwitch('disable-gpu-sandbox')
app.commandLine.appendSwitch('no-sandbox')
// Lets the file:// app page load the user's file:// video without disabling
// web security wholesale (replaces the removed webSecurity:false).
app.commandLine.appendSwitch('allow-file-access-from-files')

// Single-instance lock — prevents duplicate processes (a crash trigger).
if (!app.requestSingleInstanceLock()) {
  app.quit()
}

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
      // webSecurity:true to match the working Z-BOY/Kickflip apps — the only
      // config that differed. The video player loads file:// paths; we keep
      // that working with the targeted --allow-file-access-from-files switch
      // (set below) instead of disabling web security wholesale.
      webSecurity: true,
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

// Quit handling. There is a known Electron+macOS bug where the AppKit
// accessibility system queries the app's UI tree during the normal Cocoa
// teardown and dereferences a freed object → SIGSEGV ("quit unexpectedly").
// We sidestep it: kill the backend, then hard-exit with app.exit(0), which
// terminates the process immediately and never enters the buggy teardown path.
let hardExiting = false
function hardQuit() {
  if (hardExiting) return
  hardExiting = true
  isQuitting = true
  killBackend()
  // Give SIGTERM a moment to reach the Python child, then exit hard.
  setTimeout(() => app.exit(0), 150)
}

app.on('before-quit', (e) => {
  if (!hardExiting) {
    e.preventDefault()   // stop the normal (crash-prone) quit
    hardQuit()
  }
})

app.on('window-all-closed', () => {
  hardQuit()             // closing the window quits the app (and cleanly)
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
