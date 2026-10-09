const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("lm", {
  getConfig: () => ipcRenderer.invoke("lm:get-config"),
  saveServer: (url, authOrigins) => ipcRenderer.invoke("lm:save-server", url, authOrigins),
  finishWelcome: (pathname) => ipcRenderer.invoke("lm:finish-welcome", pathname),
  saveToken: (token) => ipcRenderer.invoke("lm:save-token", token),
  listMeetings: () => ipcRenderer.invoke("lm:list-meetings"),
  chooseMeeting: (id, title) => ipcRenderer.invoke("lm:choose-meeting", id, title),
  openZoom: (link) => ipcRenderer.invoke("lm:open-zoom", link),
  stopCapture: () => ipcRenderer.invoke("lm:stop-capture"),
  openMain: (pathname) => ipcRenderer.invoke("lm:open-main", pathname),
  openCapture: () => ipcRenderer.invoke("lm:open-capture"),
  setFloat: (on) => ipcRenderer.invoke("lm:set-float", on),
  checkUpdates: () => ipcRenderer.invoke("lm:check-updates"),
  installUpdate: () => ipcRenderer.invoke("lm:install-update"),
  showMenu: (name, x, y) => ipcRenderer.invoke("lm:menu", name, x, y),
  onState: (fn) => ipcRenderer.on("lm:state", (_e, state) => fn(state))
});
