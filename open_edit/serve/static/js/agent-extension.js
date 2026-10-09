/* Optional built-in agent extension. Review mode never imports chat or WS code. */
import { state } from './state.js';
let extension = {};
let loading;
export function loadAgentExtension() {
  return loading ||= Promise.all([import('./chat.js'), import('./ws.js')]).then(([chat, ws]) => {
    extension = { ...chat, ...ws };
    return extension;
  });
}
function reviewStatus() {
  const dot = document.querySelector('#conn-status');
  if (dot) { dot.className = 'conn-status connected'; dot.title = 'Review Studio connected'; }
}
export function clearChatLog(...args) { if (extension.clearChatLog) return extension.clearChatLog(...args);  }
export function appendUserMessage(...args) { if (extension.appendUserMessage) return extension.appendUserMessage(...args);  }
export function createChatStatus(...args) { if (extension.createChatStatus) return extension.createChatStatus(...args);  }
export function createCostBadge(...args) { if (extension.createCostBadge) return extension.createCostBadge(...args);  }
export function createVerifyChip(...args) { if (extension.createVerifyChip) return extension.createVerifyChip(...args);  }
export function sendChatMessage(...args) { if (extension.sendChatMessage) return extension.sendChatMessage(...args);  }
export function appendSearchResults(...args) { if (extension.appendSearchResults) return extension.appendSearchResults(...args);  }
export function markTurnDone(...args) { if (extension.markTurnDone) return extension.markTurnDone(...args);  }
export function setTurnActive(...args) { if (extension.setTurnActive) return extension.setTurnActive(...args);  }
export function connectWS(...args) { if (extension.connectWS) return extension.connectWS(...args);  }
export function disconnectWS(...args) { if (extension.disconnectWS) return extension.disconnectWS(...args);  }
export function setReviewConnStatus(...args) { if (extension.setReviewConnStatus) return extension.setReviewConnStatus(...args); return reviewStatus(); }
export function setWsState(...args) { if (extension.setWsState) return extension.setWsState(...args); if (args[0]) state.wsState = args[0]; }
export function setOnTurnDone(...args) { if (extension.setOnTurnDone) return extension.setOnTurnDone(...args);  }
export function scheduleReconnect(...args) { if (extension.scheduleReconnect) return extension.scheduleReconnect(...args);  }
