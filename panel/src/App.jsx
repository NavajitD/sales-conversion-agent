import { Navigate, Route, Routes } from 'react-router-dom';
import AppShell from './components/AppShell';
import AnalyticsPage from './pages/AnalyticsPage';
import CallHistoryPage from './pages/CallHistoryPage';
import CallbacksPage from './pages/CallbacksPage';
import LiveMonitorPage from './pages/LiveMonitorPage';
import ParentsPage from './pages/ParentsPage';

export default function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<Navigate to="/live-monitor" replace />} />
        <Route path="/live-monitor" element={<LiveMonitorPage />} />
        <Route path="/parents" element={<ParentsPage />} />
        <Route path="/call-history" element={<CallHistoryPage />} />
        <Route path="/callbacks" element={<CallbacksPage />} />
        <Route path="/analytics" element={<AnalyticsPage />} />
      </Route>
    </Routes>
  );
}
