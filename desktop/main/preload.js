'use strict';

/**
 * Minimal preload bridge. The renderer may:
 *  - receive startup status strings (desktop:status),
 *  - submit the first-run form (desktop:setup-submit -> Promise).
 * Nothing else is exposed: no filesystem, no process control, no secrets.
 */

const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('desktopBridge', {
  onStatus(callback) {
    if (typeof callback !== 'function') return () => {};
    const listener = (_event, message) => callback(String(message));
    ipcRenderer.on('desktop:status', listener);
    return () => ipcRenderer.removeListener('desktop:status', listener);
  },
  submitSetup(fields) {
    return ipcRenderer.invoke('desktop:setup-submit', fields);
  },
});
