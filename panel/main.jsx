import React from 'react';
import ReactDOM from 'react-dom/client';
import LiveReasoningPanel from './LiveReasoningPanel.jsx';

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <LiveReasoningPanel />
  </React.StrictMode>
);

// Wire live WebSocket → window.__ingestCallState
const WS_URL = import.meta.env.VITE_WS_URL || 'ws://localhost:3000/panel';

function connectPanel() {
  const ws = new WebSocket(WS_URL);

  ws.onopen = () => console.log('[panel] WS connected');

  ws.onmessage = (e) => {
    try {
      const event = JSON.parse(e.data);
      if (typeof window.__ingestCallState === 'function') {
        window.__ingestCallState(event);
      }
    } catch (err) {
      console.warn('[panel] bad message', err);
    }
  };

  ws.onerror = (err) => console.warn('[panel] WS error', err);

  // Reconnect on drop so the panel stays live through demo restarts
  ws.onclose = () => {
    console.log('[panel] WS closed, reconnecting in 2s...');
    setTimeout(connectPanel, 2000);
  };
}

connectPanel();
