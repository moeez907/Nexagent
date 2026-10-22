const { contextBridge } = require('electron');

contextBridge.exposeInMainWorld('autonomousWebAgent', {
  desktop: true,
  platform: process.platform,
});
