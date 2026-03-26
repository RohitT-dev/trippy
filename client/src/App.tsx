import { useState } from 'react';
import { Routes, Route, Navigate, useNavigate } from 'react-router-dom';
import { TripChatPage } from './pages/TripChatPage';
import { PreferencesPage } from './pages/PreferencesPage';
import { LoginPage } from './pages/LoginPage';
import { useAuth } from './context/AuthContext';
import { useTravelStore } from './store/useTravelStore';
import './App.css';

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center">
        <div className="text-slate-400 text-sm font-medium">Loading…</div>
      </div>
    );
  }

  return user ? <>{children}</> : <Navigate to="/login" replace />;
}

type Page = 'plan' | 'preferences';

function AppShell() {
  const [activePage, setActivePage] = useState<Page>('plan');
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const status = useTravelStore((s) => s.ui_status);
  const isPlanning = status !== 'pending' && status !== 'error' && status !== 'stopped' && status !== 'complete';

  const handleLogout = async () => {
    await logout();
    navigate('/login');
  };

  return (
    <div className="min-h-screen bg-slate-50 font-sans">
      {/* ── Top Navigation Bar (Horizon Bound) ── */}
      <nav className="fixed top-0 left-0 right-0 z-50 h-16 bg-white/80 backdrop-blur-xl border-b border-slate-200">
        <div className="max-w-5xl mx-auto h-full px-6 flex items-center justify-between">
          {/* Brand */}
          <button
            onClick={() => setActivePage('plan')}
            className="flex items-center gap-2 focus:outline-none"
          >
            <span className="text-xl">✈️</span>
            <span className="text-lg font-bold text-slate-900 tracking-tight">Trippy</span>
          </button>

          {/* Center pill nav */}
          <div className="hidden sm:flex items-center gap-1 bg-slate-100 rounded-lg p-1">
            {(['plan', 'preferences'] as Page[]).map((page) => (
              <button
                key={page}
                onClick={() => !isPlanning && setActivePage(page)}
                disabled={isPlanning && page !== activePage}
                className={`px-4 py-1.5 rounded-md text-sm font-semibold transition-all ${
                  activePage === page
                    ? 'bg-white text-slate-900 shadow-sm'
                    : 'text-slate-500 hover:text-slate-800 disabled:opacity-40 disabled:cursor-not-allowed'
                }`}
              >
                {page === 'plan' ? 'Plan a Trip' : 'Preferences'}
              </button>
            ))}
          </div>

          {/* Right: user info + logout */}
          <div className="flex items-center gap-3">
            {user && (
              <span className="text-xs text-slate-400 hidden sm:inline truncate max-w-[140px]">
                {user.email}
              </span>
            )}
            <button
              onClick={handleLogout}
              className="px-3 py-1.5 rounded-lg text-xs font-semibold text-slate-500 border border-slate-200 hover:bg-slate-50 transition-colors"
            >
              Sign out
            </button>
          </div>
        </div>
      </nav>

      {/* Page content */}
      <main className="pt-16">
        {activePage === 'plan' ? (
          <TripChatPage onGoToPreferences={() => setActivePage('preferences')} />
        ) : (
          <PreferencesPage onDone={() => setActivePage('plan')} />
        )}
      </main>
    </div>
  );
}

function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        path="/*"
        element={
          <ProtectedRoute>
            <AppShell />
          </ProtectedRoute>
        }
      />
    </Routes>
  );
}

export default App;
