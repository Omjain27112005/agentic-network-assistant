// Custom WebSocket hook — auto-connects, auto-reconnects, updates Zustand store
import { useEffect, useRef } from 'react';
import { useNetworkStore } from '../store/networkStore';

const WS_URL = 'ws://localhost:8000/ws/live';
const RECONNECT_DELAY = 3000;

export function useWebSocket() {
  const wsRef = useRef(null);
  const reconnectRef = useRef(null);
  const setLiveData = useNetworkStore((s) => s.setLiveData);
  const setWsConnected = useNetworkStore((s) => s.setWsConnected);

  useEffect(() => {
    function connect() {
      wsRef.current = new WebSocket(WS_URL);

      wsRef.current.onopen = () => {
        setWsConnected(true);
        console.log('[WS] Connected');
        if (reconnectRef.current) {
          clearTimeout(reconnectRef.current);
          reconnectRef.current = null;
        }
      };

      wsRef.current.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.type === 'live_update') {
            setLiveData(data);
          }
        } catch (e) {
          console.error('[WS] Parse error:', e);
        }
      };

      wsRef.current.onclose = () => {
        setWsConnected(false);
        console.log('[WS] Disconnected — reconnecting in 3s...');
        reconnectRef.current = setTimeout(connect, RECONNECT_DELAY);
      };

      wsRef.current.onerror = (err) => {
        console.error('[WS] Error:', err);
        wsRef.current?.close();
      };
    }

    connect();

    return () => {
      if (reconnectRef.current) clearTimeout(reconnectRef.current);
      wsRef.current?.close();
    };
  }, []);
}
