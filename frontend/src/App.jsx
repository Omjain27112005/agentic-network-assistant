import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Sidebar from './components/Sidebar';
import Dashboard from './pages/Dashboard';
import Alerts from './pages/Alerts';
import Incidents from './pages/Incidents';
import Chat from './pages/Chat';
import { useWebSocket } from './hooks/useWebSocket';

function AppLayout({ children }) {
  return (
    <div className="app-layout">
      <Sidebar />
      <main className="main-content">{children}</main>
    </div>
  );
}

export default function App() {
  // Initialize WebSocket connection — runs once, updates Zustand store globally
  useWebSocket();

  return (
    <BrowserRouter>
      <AppLayout>
        <Routes>
          <Route path="/"          element={<Dashboard />} />
          <Route path="/alerts"    element={<Alerts />} />
          <Route path="/incidents" element={<Incidents />} />
          <Route path="/chat"      element={<Chat />} />
        </Routes>
      </AppLayout>
    </BrowserRouter>
  );
}
