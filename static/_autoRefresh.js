import { loadStatus } from "./_device.js";
import { loadDeviceData } from "./_device.js";
import { configCache } from "./_device.js";
import { CACHE_TTL } from "./_update.js";

// ---------------------------------------------------------------------------
// one timer for everything
// ---------------------------------------------------------------------------
let timer = null;

const RATE = {
  status: 5_000,
  device: 5_000,
  config: CACHE_TTL,
  desktop: 5_000, // merged Status+Device view
};

function tick(key) {
  switch (key) {
    case "status":
      loadStatus();
      break;
    case "device":
      loadDeviceData();
      break;
    case "config":
      configCache.get();
      break;
    case "desktop": // desktop == status + device
      loadStatus();
      loadDeviceData();
      break;
  }
}

export function scheduleRefresh(key, { immediate = true } = {}) {
  clearInterval(timer);
  const rate = RATE[key];
  if (!rate) return;
  if (immediate) tick(key);
  timer = setInterval(() => tick(key), rate);
}
