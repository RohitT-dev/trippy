import { useState } from 'react';
import { TripChatPage } from './pages/TripChatPage';
import { PreferencesPage } from './pages/PreferencesPage';
import { useTravelStore } from './store/useTravelStore';
import './App.css';

type Page = 'plan' | 'preferences';

function App() {
  const [activePage, setActivePage] = useState<Page>('plan');
  const status = useTravelStore((s) => s.ui_status);
  const isPlanning = status !== 'pending' && status !== 'error' && status !== 'stopped' && status !== 'complete';

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

          {/* Right CTA */}
          <button
            onClick={() => setActivePage('plan')}
            className="px-4 py-2 rounded-lg text-sm font-semibold text-white bg-primary hover:bg-primary-dark active:scale-95 transition-all shadow-sm"
          >
            New Trip
          </button>
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

export default App;
