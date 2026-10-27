'use strict';
const { contextBridge, ipcRenderer } = require('electron');
contextBridge.exposeInMainWorld('mortar', {
  newest: () => ipcRenderer.invoke('newest'),
  gpu: () => ipcRenderer.invoke('gpu'),
  drives: () => ipcRenderer.invoke('drives'),
  chooseIso: () => ipcRenderer.invoke('chooseIso'),
  make: (req) => ipcRenderer.invoke('make', req),
  cancel: () => ipcRenderer.invoke('cancel'),
  open: (what) => ipcRenderer.invoke('open', what),
  onProgress: (cb) => ipcRenderer.on('progress', (_e, p) => cb(p)),
  platform: process.platform,
});
