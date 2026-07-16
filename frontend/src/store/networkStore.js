// Zustand store — global state for live network data
// All components read from here. WebSocket updates this store.
import { create } from 'zustand';

export const useNetworkStore = create((set) => ({
  // Live data from WebSocket
  healthScore: 100,
  devices: [],
  alerts: [],
  alertCount: 0,
  wsConnected: false,
  lastUpdated: null,

  // Incidents from REST API
  incidents: [],

  // Chat
  chatSessions: {},

  // Actions
  setLiveData: (data) => set({
    healthScore: data.health_score,
    devices: data.devices,
    alerts: data.alerts,
    alertCount: data.alert_count,
    lastUpdated: new Date(),
  }),
  setWsConnected: (connected) => set({ wsConnected: connected }),
  setIncidents: (incidents) => set({ incidents }),
  addChatMessage: (sessionId, message) => set((state) => ({
    chatSessions: {
      ...state.chatSessions,
      [sessionId]: [...(state.chatSessions[sessionId] || []), message],
    },
  })),
}));
