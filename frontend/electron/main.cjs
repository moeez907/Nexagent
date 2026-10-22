const { app, BrowserWindow, BrowserView, session } = require('electron');
const path = require('path');

const isDevelopment = !app.isPackaged;
const frontendUrl = process.env.AWA_FRONTEND_URL || 'http://localhost:5173';
const cdpPort = Number(process.env.AWA_CDP_PORT || 9222);

app.commandLine.appendSwitch('remote-debugging-port', String(cdpPort));
app.commandLine.appendSwitch('remote-allow-origins', '*');

function createWindow() {
  const window = new BrowserWindow({
    width: 1440,
    height: 920,
    minWidth: 980,
    minHeight: 680,
    backgroundColor: '#202123',
    title: 'Nexagent',
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      contextIsolation: true,
      sandbox: true,
      webviewTag: true,
    },
  });

  const browserView = new BrowserView({
    webPreferences: {
      contextIsolation: true,
      sandbox: true,
    },
  });
  window.setBrowserView(browserView);

  const resizeBrowserView = () => {
    const [width, height] = window.getContentSize();
    browserView.setBounds({
      x: Math.floor(width * 0.62),
      y: 58,
      width: Math.ceil(width * 0.38),
      height: Math.max(300, height - 58),
    });
    browserView.setAutoResize({ width: true, height: true });
  };
  window.on('resize', resizeBrowserView);
  resizeBrowserView();
  browserView.webContents.loadURL('about:blank');

  if (isDevelopment) {
    window.loadURL(frontendUrl);
  } else {
    window.loadFile(path.join(__dirname, '../dist/index.html'));
  }

  window.webContents.setWindowOpenHandler(({ url }) => {
    window.loadURL(url);
    return { action: 'deny' };
  });
}

app.whenReady().then(() => {
  session.defaultSession.setPermissionRequestHandler((_webContents, _permission, callback) => callback(true));
  createWindow();
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});
