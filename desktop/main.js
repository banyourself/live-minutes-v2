const { app, BrowserWindow, dialog, ipcMain, Menu, safeStorage, screen, session, shell, WebContentsView } = require("electron");
const fs = require("fs");
const path = require("path");
const { fileURLToPath } = require("url");
const { zoomWebUrl } = require("./zoom-url");

const DEFAULT_SERVER = "https://minutes.kevinle.tech";
const CHROME_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/" +
  process.versions.chrome + " Safari/537.36";
const ZOOM_APP = "https://app.zoom.us";
const TURNSTILE = "https://challenges.cloudflare.com";
const SIGN_IN = ["https://accounts.google.com", "https://login.microsoftonline.com", "https://login.live.com"];
const BG = "#0a111f";
const BAR = 36;
const ICON = path.join(__dirname, "icon.png");
const configPath = () => path.join(app.getPath("userData"), "config.json");
const samePath = (p) => process.platform === "win32" ? path.resolve(p).toLowerCase() : path.resolve(p);
const LOCAL_PAGES = ["welcome.html", "capture.html", "float.html", "titlebar.html"].map((f) => samePath(path.join(__dirname, f)));
const APP_PATH = /^\/(?!\/)[A-Za-z0-9\-._~/?=&%]*$/;
let welcomeWin = null;
let mainWin = null;
let mainView = null;
let captureWin = null;
let floatWin = null;
let zoomWin = null;
const capture = { meetingId: "", meetingTitle: "", organization: "", phase: "idle", startedAt: 0, lines: 0, lastLine: "",
  drafting: false, error: "" };
const update = { status: "idle", version: "", percent: 0, error: "" };
const UPDATE_EVERY = 6 * 3600 * 1000;
let updater = null;
let manualCheck = false;
let restartAsked = "";

function readConfig() {
  try {
    return JSON.parse(fs.readFileSync(configPath(), "utf8"));
  } catch {
    return {};
  }
}

function writeConfig(cfg) {
  fs.mkdirSync(path.dirname(configPath()), { recursive: true });
  fs.writeFileSync(configPath(), JSON.stringify(cfg, null, 2));
}

function updateConfig(patch) {
  const cfg = { ...readConfig(), ...patch };
  Object.keys(patch).forEach((k) => { if (patch[k] === undefined) delete cfg[k]; });
  writeConfig(cfg);
  return cfg;
}

function getToken() {
  const enc = readConfig().captureToken;
  if (!enc) return "";
  try {
    return safeStorage.isEncryptionAvailable() ? safeStorage.decryptString(Buffer.from(enc, "base64")) : "";
  } catch {
    return "";
  }
}

function setToken(token) {
  updateConfig({ captureToken: token && safeStorage.isEncryptionAvailable() ? safeStorage.encryptString(token).toString("base64") : "" });
}

function cleanServerUrl(raw) {
  try {
    const u = new URL(String(raw || "").trim());
    const local = u.protocol === "http:" && ["localhost", "127.0.0.1"].includes(u.hostname);
    return u.protocol === "https:" || local ? (u.origin + u.pathname).replace(/\/+$/, "") : "";
  } catch {
    return "";
  }
}

function serverUrl() {
  return cleanServerUrl(readConfig().serverUrl) || DEFAULT_SERVER;
}

function httpsOrigin(entry) {
  try {
    const u = new URL(String(entry).trim());
    const bare = u.pathname === "/" && !u.search && !u.hash && !u.username && !u.password;
    return u.protocol === "https:" && bare && /^[a-z0-9.-]+$/.test(u.hostname) ? u.origin : "";
  } catch {
    return "";
  }
}

function parseAuthOrigins(raw) {
  const list = [];
  for (const entry of String(raw || "").split(/[\s,]+/).filter(Boolean)) {
    const o = httpsOrigin(entry);
    if (!o) return { error: entry + " is not a valid https sign-in address, for example https://login.yourdistrict.edu" };
    if (!list.includes(o)) list.push(o);
  }
  return { list };
}

function authOrigins() {
  const saved = readConfig().authOrigins;
  return Array.isArray(saved) ? saved.map(httpsOrigin).filter(Boolean) : [];
}

function originOf(url) {
  try {
    return new URL(url).origin;
  } catch {
    return "";
  }
}

function webUrl(url) {
  try {
    const u = new URL(url);
    return ["http:", "https:"].includes(u.protocol) ? u.href : "";
  } catch {
    return "";
  }
}

function openWeb(url) {
  const href = webUrl(url);
  if (href) void shell.openExternal(href);
}

const isServer = (o) => !!o && o === originOf(serverUrl());
const isZoom = (o) => o === "https://zoom.us" || (o.startsWith("https://") && o.endsWith(".zoom.us"));
const isSignIn = (o) => SIGN_IN.includes(o) || isZoom(o) || authOrigins().includes(o);
const mainAllowed = (o, main, top) => main ? isServer(o) || isSignIn(o) : !isServer(top) || isServer(o) || o === TURNSTILE;
const floatOn = () => readConfig().floatOn !== false;

function lockNavigation(win, allowed) {
  const wc = win.webContents;
  wc.setWindowOpenHandler(({ url }) => {
    openWeb(url);
    return { action: "deny" };
  });
  const guard = (e) => {
    if (allowed(originOf(e.url), e.isMainFrame, originOf(wc.getURL()))) return;
    e.preventDefault();
    if (e.isMainFrame) openWeb(e.url);
  };
  wc.on("will-frame-navigate", guard);
  wc.on("will-redirect", guard);
}

function lockPermissions() {
  const ok = (permission, url) => permission === "clipboard-sanitized-write" && isServer(originOf(url));
  session.defaultSession.setPermissionRequestHandler((wc, permission, cb, details) => {
    cb(ok(permission, (details && details.requestingUrl) || wc.getURL()));
  });
  session.defaultSession.setPermissionCheckHandler((_wc, permission, origin) => ok(permission, origin));
}

function topFrameUrl(e) {
  try {
    return e.senderFrame && !e.senderFrame.parent ? e.senderFrame.url : "";
  } catch {
    return "";
  }
}

function fromLocalPage(e) {
  try {
    return LOCAL_PAGES.includes(samePath(fileURLToPath(topFrameUrl(e))));
  } catch {
    return false;
  }
}

function fromZoom(e) {
  return originOf(topFrameUrl(e)) === ZOOM_APP && !!zoomWin && !zoomWin.isDestroyed() && e.sender === zoomWin.webContents;
}

function localWindow(file, options, hash) {
  const win = new BrowserWindow({
    backgroundColor: BG, icon: ICON, autoHideMenuBar: true, titleBarStyle: "hidden",
    titleBarOverlay: { color: BG, symbolColor: "#e8eef8", height: BAR },
    ...options,
    webPreferences: { preload: path.join(__dirname, "preload.js"), contextIsolation: true, sandbox: true, nodeIntegration: false }
  });
  lockNavigation(win, () => false);
  void win.loadFile(path.join(__dirname, file), hash ? { hash } : undefined);
  return win;
}

function closeFloatIfAlone() {
  if (floatWin && BrowserWindow.getAllWindows().every((w) => w === floatWin)) floatWin.destroy();
}

function openWelcome(hash) {
  if (welcomeWin) { welcomeWin.focus(); return welcomeWin; }
  welcomeWin = localWindow("welcome.html", { width: 1040, height: 680, minWidth: 560, minHeight: 560, title: "Live Minutes" }, hash);
  welcomeWin.on("closed", () => { welcomeWin = null; closeFloatIfAlone(); });
  return welcomeWin;
}

function openMain(pathname) {
  const url = serverUrl() + (pathname && APP_PATH.test(pathname) ? pathname : "/dashboard");
  if (mainWin) {
    void mainView.webContents.loadURL(url);
    if (mainWin.isMinimized()) mainWin.restore();
    mainWin.focus();
    return mainWin;
  }
  mainWin = localWindow("titlebar.html", { width: 1360, height: 880, title: "Live Minutes" });
  mainWin.setAutoHideMenuBar(false);
  mainWin.setMenuBarVisibility(false);
  mainView = new WebContentsView({ webPreferences: { contextIsolation: true, sandbox: true, nodeIntegration: false } });
  mainView.setBackgroundColor(BG);
  mainWin.contentView.addChildView(mainView);
  const fit = () => {
    const [width, height] = mainWin.getContentSize();
    const top = mainWin.isFullScreen() ? 0 : BAR;
    mainView.setBounds({ x: 0, y: top, width, height: Math.max(0, height - top) });
  };
  fit();
  ["resize", "maximize", "unmaximize", "enter-full-screen", "leave-full-screen"].forEach((e) => mainWin.on(e, fit));
  mainWin.on("focus", () => mainView.webContents.focus());
  mainView.webContents.on("page-title-updated", (_e, title) => mainWin.setTitle(title));
  mainView.webContents.setUserAgent(mainView.webContents.getUserAgent() + " LiveMinutesDesktop/" + app.getVersion());
  mainView.webContents.on("will-frame-navigate", (e) => {
    if (!e.isMainFrame || !isServer(originOf(e.url)) || new URL(e.url).pathname !== "/desktop/tour") return;
    e.preventDefault();
    openWelcome();
  });
  lockNavigation(mainView, mainAllowed);
  void mainView.webContents.loadURL(url);
  mainWin.on("closed", () => { mainView.webContents.close(); mainWin = null; mainView = null; closeFloatIfAlone(); });
  return mainWin;
}

function openCapture() {
  if (captureWin) { captureWin.focus(); return captureWin; }
  captureWin = localWindow("capture.html", { width: 460, height: 760, minWidth: 400, minHeight: 520, title: "Live capture · Live Minutes" });
  captureWin.on("closed", () => { captureWin = null; closeFloatIfAlone(); });
  return captureWin;
}

function placeFloat(win) {
  const area = screen.getPrimaryDisplay().workArea;
  const [w] = win.getSize();
  win.setPosition(Math.round(area.x + (area.width - w) / 2), area.y + 10);
}

function updateFloat() {
  const want = floatOn() && !!zoomWin && ["zoom", "live", "paused"].includes(capture.phase);
  if (!want) {
    if (floatWin) floatWin.hide();
    return;
  }
  if (!floatWin) {
    floatWin = new BrowserWindow({
      width: 600, height: 60, frame: false, transparent: true, resizable: false, maximizable: false, minimizable: false,
      fullscreenable: false, skipTaskbar: true, alwaysOnTop: true, hasShadow: false, show: false, title: "Live Minutes bar", icon: ICON,
      webPreferences: { preload: path.join(__dirname, "preload.js"), contextIsolation: true, sandbox: true, nodeIntegration: false }
    });
    floatWin.setAlwaysOnTop(true, "floating");
    lockNavigation(floatWin, () => false);
    void floatWin.loadFile(path.join(__dirname, "float.html"));
    floatWin.once("ready-to-show", () => { placeFloat(floatWin); floatWin.showInactive(); });
    floatWin.on("closed", () => { floatWin = null; });
    return;
  }
  if (!floatWin.isVisible()) floatWin.showInactive();
}

function publicState() {
  return { ...capture, hasToken: !!getToken(), floatOn: floatOn(), version: app.getVersion(), update: { ...update } };
}

function broadcast() {
  const s = publicState();
  [captureWin, floatWin, welcomeWin].forEach((w) => { if (w && !w.isDestroyed()) w.webContents.send("lm:state", s); });
  updateFloat();
}

function setUpdate(patch) {
  Object.assign(update, patch);
  const bar = update.status === "downloading" ? Math.max(0.01, update.percent / 100) : -1;
  [mainWin, captureWin].forEach((w) => { if (w && !w.isDestroyed()) w.setProgressBar(bar); });
  broadcast();
}

function anchorWindow() {
  return [mainWin, captureWin, welcomeWin].find((w) => w && !w.isDestroyed() && w.isVisible()) || undefined;
}

async function askRestart(manual) {
  if (update.status !== "ready" || (!manual && capture.phase === "live") || (!manual && restartAsked === update.version)) return;
  restartAsked = update.version;
  const r = await dialog.showMessageBox(anchorWindow(), {
    type: "info", buttons: ["Restart now", "Later"], defaultId: 0, cancelId: 1, title: "Update ready", icon: ICON,
    message: "Live Minutes " + update.version + " is ready to install.",
    detail: "Restart to finish updating. If you choose Later, it installs the next time you close Live Minutes."
  });
  if (r.response === 0) installUpdate();
}

function installUpdate() {
  if (updater && update.status === "ready") setImmediate(() => updater.quitAndInstall(false, true));
}

function setupUpdates() {
  if (!app.isPackaged) return;
  ({ autoUpdater: updater } = require("electron-updater"));
  updater.autoDownload = true;
  updater.autoInstallOnAppQuit = true;
  updater.disableDifferentialDownload = true;
  updater.on("checking-for-update", () => setUpdate({ status: "checking", error: "" }));
  updater.on("update-available", (info) => setUpdate({ status: "downloading", version: info.version, percent: 0 }));
  updater.on("download-progress", (p) => setUpdate({ status: "downloading", percent: Math.round(p.percent || 0) }));
  updater.on("update-not-available", () => {
    setUpdate({ status: "current", error: "" });
    if (manualCheck) void dialog.showMessageBox(anchorWindow(), { type: "info", title: "No updates", icon: ICON,
      message: "Live Minutes is up to date.", detail: "You have version " + app.getVersion() + ", the newest one." });
    manualCheck = false;
  });
  updater.on("update-downloaded", (info) => {
    setUpdate({ status: "ready", version: info.version, percent: 100 });
    void askRestart(manualCheck);
    manualCheck = false;
  });
  updater.on("error", () => {
    setUpdate({ status: "error", error: "The update could not be checked or downloaded. Try again later." });
    if (manualCheck) void dialog.showMessageBox(anchorWindow(), { type: "warning", title: "Update failed", icon: ICON,
      message: "Live Minutes could not check for or download the update.",
      detail: "Nothing was installed. Check your internet connection and try again later." });
    manualCheck = false;
  });
  setTimeout(() => checkUpdates(false), 15000);
  setInterval(() => checkUpdates(false), UPDATE_EVERY);
}

function checkUpdates(manual) {
  if (!updater) {
    if (manual) void dialog.showMessageBox(anchorWindow(), { type: "info", title: "Updates", icon: ICON,
      message: "Updates are checked in the installed app.", detail: "This copy is running from source." });
    return;
  }
  if (update.status === "ready") { if (manual) void askRestart(true); return; }
  if (["checking", "downloading"].includes(update.status)) return;
  manualCheck = manual;
  updater.checkForUpdates().catch(() => undefined);
}

function resetCapture() {
  Object.assign(capture, { startedAt: 0, lines: 0, lastLine: "", drafting: false, error: "" });
}

function openZoom(link) {
  const url = zoomWebUrl(link);
  if (!url) return { ok: false, error: "Paste a Zoom meeting link or a 9 to 12 digit meeting ID." };
  if (zoomWin) zoomWin.close();
  const part = session.fromPartition("persist:zoom");
  part.setUserAgent(CHROME_UA);
  part.setPermissionRequestHandler((wc, permission, cb) => {
    cb(isZoom(originOf(wc.getURL())) && ["media", "notifications", "clipboard-sanitized-write"].includes(permission));
  });
  const win = new BrowserWindow({
    width: 1280, height: 820, title: "Zoom · Live Minutes", icon: ICON, backgroundColor: BG,
    webPreferences: { partition: "persist:zoom", preload: path.join(__dirname, "capture-preload.js"),
      contextIsolation: true, sandbox: true, nodeIntegration: false }
  });
  zoomWin = win;
  lockNavigation(win, (o, main) => !main || isZoom(o));
  void win.loadURL(url, { userAgent: CHROME_UA });
  win.on("closed", () => {
    if (zoomWin !== win) return;
    zoomWin = null;
    capture.phase = capture.meetingId ? "ready" : "idle";
    broadcast();
    closeFloatIfAlone();
    void askRestart(false);
  });
  capture.phase = "zoom";
  capture.error = "";
  broadcast();
  return { ok: true };
}

async function api(pathname, opts = {}) {
  const token = getToken();
  if (!token) throw Object.assign(new Error("Connect this computer with a capture token first."), { status: 0 });
  const res = await fetch(serverUrl() + pathname, {
    ...opts,
    headers: { "Content-Type": "application/json", "X-Capture-Token": token, ...(opts.headers || {}) }
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw Object.assign(new Error(body.detail || "Live Minutes answered " + res.status), { status: res.status });
  return body;
}

function friendly(e) {
  if (e.status === 401 || e.status === 403) return "Live Minutes did not accept this token. Create a new one under Settings, Capture devices.";
  if (!e.status && /fetch failed|ENOTFOUND|ECONN/i.test(e.message)) return "Could not reach " + serverUrl().replace(/^https?:\/\//, "") + ". Check your internet connection.";
  return e.message;
}

function lastLine(text) {
  const rows = String(text || "").split(/\r?\n/).map((s) => s.trim()).filter(Boolean);
  return (rows[rows.length - 1] || "").slice(0, 240);
}

function handle(channel, trusted, fn) {
  ipcMain.handle(channel, (e, ...args) => trusted(e) ? fn(...args) : { ok: false, error: "Blocked a request from an untrusted page." });
}

handle("lm:get-config", fromLocalPage, () => {
  const cfg = readConfig();
  return { serverUrl: serverUrl(), customServer: !!cleanServerUrl(cfg.serverUrl), authOrigins: authOrigins(),
    version: app.getVersion(), onboarded: !!cfg.onboarded, state: publicState() };
});

handle("lm:save-server", fromLocalPage, (url, extra) => {
  const raw = String(url || "").trim();
  const clean = raw ? cleanServerUrl(raw) : "";
  if (raw && !clean) return { ok: false, error: "Enter the full address starting with https:// (http:// works only for localhost)." };
  const auth = parseAuthOrigins(extra);
  if (auth.error) return { ok: false, error: auth.error };
  const before = serverUrl();
  updateConfig({ serverUrl: clean || undefined, authOrigins: auth.list });
  if (serverUrl() !== before) {
    capture.organization = "";
    if (mainView) void mainView.webContents.loadURL(serverUrl() + "/dashboard");
    broadcast();
  }
  return { ok: true };
});

handle("lm:finish-welcome", fromLocalPage, (pathname) => {
  updateConfig({ onboarded: true });
  openMain(String(pathname || ""));
  if (welcomeWin) welcomeWin.close();
  return { ok: true };
});

handle("lm:save-token", fromLocalPage, async (token) => {
  const value = String(token || "").trim();
  if (!value) return { ok: false, error: "Paste a capture token first." };
  setToken(value);
  try {
    const r = await api("/api/capture/meetings");
    capture.organization = String(r.organization || "");
    broadcast();
    return { ok: true, organization: capture.organization };
  } catch (e) {
    if (e.status === 401 || e.status === 403) setToken("");
    capture.organization = "";
    broadcast();
    return { ok: false, error: friendly(e) };
  }
});

handle("lm:list-meetings", fromLocalPage, async () => {
  try {
    const r = await api("/api/capture/meetings");
    capture.organization = String(r.organization || "");
    broadcast();
    return { ok: true, organization: r.organization, meetings: r.meetings || [] };
  } catch (e) {
    return { ok: false, error: friendly(e) };
  }
});

handle("lm:choose-meeting", fromLocalPage, (id, title) => {
  const next = String(id || "");
  if (next !== capture.meetingId) resetCapture();
  capture.meetingId = next;
  capture.meetingTitle = String(title || "").slice(0, 200);
  if (!zoomWin) capture.phase = next ? "ready" : "idle";
  broadcast();
  return { ok: true };
});

handle("lm:open-zoom", fromLocalPage, (link) => openZoom(link));

handle("lm:stop-capture", fromLocalPage, () => {
  if (zoomWin) zoomWin.webContents.send("lm:command", "stop");
  capture.phase = zoomWin ? "paused" : capture.meetingId ? "ready" : "idle";
  broadcast();
  return { ok: true };
});

handle("lm:open-main", fromLocalPage, (pathname) => {
  openMain(String(pathname || ""));
  return { ok: true };
});

handle("lm:open-capture", fromLocalPage, () => {
  openCapture();
  return { ok: true };
});

handle("lm:set-float", fromLocalPage, (on) => {
  updateConfig({ floatOn: !!on });
  broadcast();
  buildMenu();
  return { ok: true };
});

handle("lm:check-updates", fromLocalPage, () => {
  checkUpdates(true);
  return { ok: true };
});

handle("lm:install-update", fromLocalPage, () => {
  installUpdate();
  return { ok: true };
});

handle("lm:reader", fromZoom, (status) => {
  if (status === "reading" && capture.meetingId) {
    capture.phase = "live";
    if (!capture.startedAt) capture.startedAt = Date.now();
  } else if (status === "stopped") {
    capture.phase = "paused";
    void askRestart(false);
  } else if (status === "picking") {
    capture.phase = "zoom";
  }
  broadcast();
  return { ok: true };
});

handle("lm:snapshot", fromZoom, async (text) => {
  if (!capture.meetingId) return { ok: false, error: "Choose a meeting in Live capture first." };
  try {
    const r = await api("/api/capture/meetings/" + encodeURIComponent(capture.meetingId), {
      method: "POST", body: JSON.stringify({ snapshot: String(text || "").slice(-60000) })
    });
    capture.lines += Number(r.added) || 0;
    capture.lastLine = lastLine(text) || capture.lastLine;
    capture.drafting = !!r.drafting;
    capture.error = "";
    capture.phase = "live";
    if (!capture.startedAt) capture.startedAt = Date.now();
    broadcast();
    return { ok: true, added: r.added };
  } catch (e) {
    capture.error = friendly(e);
    broadcast();
    return { ok: false, error: capture.error };
  }
});

function pageContents() {
  const win = BrowserWindow.getFocusedWindow();
  return win && win === mainWin && mainView ? mainView.webContents : win && win.webContents;
}

function zoomPage(step) {
  const wc = pageContents();
  if (wc) wc.setZoomLevel(step ? wc.getZoomLevel() + step : 0);
}

function menuTemplate() {
  return [
    { id: "file", label: "File", submenu: [
      { label: "Live capture…", accelerator: "CmdOrCtrl+Shift+C", click: () => openCapture() },
      { label: "Show the floating bar during meetings", type: "checkbox", checked: floatOn(),
        click: (item) => { updateConfig({ floatOn: item.checked }); broadcast(); } },
      { type: "separator" },
      { label: "Welcome tour", click: () => openWelcome() },
      { label: "Server settings…", click: () => openWelcome("server") },
      { type: "separator" },
      { role: "quit" }
    ] },
    { id: "view", label: "View", submenu: [
      { label: "Reload", accelerator: "CmdOrCtrl+R", click: () => { const wc = pageContents(); if (wc) wc.reload(); } },
      { role: "togglefullscreen" },
      { type: "separator" },
      { label: "Zoom In", accelerator: "CmdOrCtrl+Plus", click: () => zoomPage(0.5) },
      { label: "Zoom Out", accelerator: "CmdOrCtrl+-", click: () => zoomPage(-0.5) },
      { label: "Actual Size", accelerator: "CmdOrCtrl+0", click: () => zoomPage(0) }
    ] },
    { id: "help", label: "Help", submenu: [
      { label: "Check for updates…", click: () => checkUpdates(true) },
      { type: "separator" },
      { label: "How capture works", click: () => openMain("/help/zoom") },
      { label: "Support", click: () => openMain("/support") },
      { type: "separator" },
      { label: "About Live Minutes", click: () => void dialog.showMessageBox({
        type: "info", title: "About Live Minutes", icon: ICON, message: "Live Minutes " + app.getVersion(),
        detail: "Connected to " + serverUrl().replace(/^https?:\/\//, "") + ".\nBuilt by Kevin Le." }) }
    ] }
  ];
}

function buildMenu() {
  Menu.setApplicationMenu(Menu.buildFromTemplate(menuTemplate()));
}

ipcMain.handle("lm:menu", (e, name, x, y) => {
  const item = menuTemplate().find((m) => m.id === name);
  if (!mainWin || e.sender !== mainWin.webContents || !fromLocalPage(e) || !item || !Number.isFinite(x) || !Number.isFinite(y)) return;
  return new Promise((resolve) => Menu.buildFromTemplate(item.submenu).popup({ window: mainWin, x: Math.round(x), y: Math.round(y), callback: resolve }));
});

function focusExisting() {
  const win = mainWin || welcomeWin || BrowserWindow.getAllWindows().find((w) => w !== floatWin);
  if (!win) { start(); return; }
  if (win.isMinimized()) win.restore();
  win.focus();
}

function start() {
  if (readConfig().onboarded) openMain();
  else openWelcome();
}

app.on("web-contents-created", (_e, wc) => {
  wc.on("will-attach-webview", (e) => e.preventDefault());
  wc.setWindowOpenHandler(() => ({ action: "deny" }));
});

if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on("second-instance", focusExisting);
  app.whenReady().then(() => {
    app.setAppUserModelId("app.liveminutes.desktop");
    lockPermissions();
    buildMenu();
    start();
    setupUpdates();
    app.on("activate", () => { if (BrowserWindow.getAllWindows().length === 0) start(); });
  });
}

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});
