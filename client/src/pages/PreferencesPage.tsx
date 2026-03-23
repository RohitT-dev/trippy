/**
 * PreferencesPage — User profile + travel style + interests.
 *
 * Sections (numbered per design spec):
 *   01  About You    — name, age, country of origin
 *   02  Travel Style — budget, pace, group type & size
 *   03  Interests    — multi-select personality / interest chips → trip_theme
 */

import { useState } from 'react';
import { useTravelStore } from '../store/useTravelStore';
import { TravelPreferences } from '../store/types';

// ---------------------------------------------------------------------------
// Interest chips
// ---------------------------------------------------------------------------

const INTERESTS = [
  { id: 'adventure',    emoji: '🧗', name: 'Adventure' },
  { id: 'culture',      emoji: '🎭', name: 'Culture & Arts' },
  { id: 'food',         emoji: '🍜', name: 'Food & Drink' },
  { id: 'beach',        emoji: '🏖️', name: 'Beach & Sun' },
  { id: 'nightlife',    emoji: '🌃', name: 'Nightlife' },
  { id: 'nature',       emoji: '🌿', name: 'Nature & Wildlife' },
  { id: 'history',      emoji: '🏛️', name: 'History' },
  { id: 'shopping',     emoji: '🛍️', name: 'Shopping' },
  { id: 'wellness',     emoji: '🧘', name: 'Wellness & Spa' },
  { id: 'luxury',       emoji: '💎', name: 'Luxury' },
  { id: 'budget',       emoji: '💰', name: 'Budget Travel' },
  { id: 'photography',  emoji: '📸', name: 'Photography' },
  { id: 'family',       emoji: '👨‍👩‍👧', name: 'Family Activities' },
  { id: 'romance',      emoji: '💕', name: 'Romance' },
  { id: 'architecture', emoji: '🏗️', name: 'Architecture' },
  { id: 'festivals',    emoji: '🎉', name: 'Music & Festivals' },
];

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

interface Props {
  onDone: () => void;
}

export const PreferencesPage = ({ onDone }: Props) => {
  const store = useTravelStore();

  const [name, setName] = useState(store.userProfile?.name ?? '');
  const [age, setAge] = useState(store.userProfile?.age ?? '');
  const [prefs, setPrefs] = useState<TravelPreferences>({ ...store.preferences });
  const [selectedInterests, setSelectedInterests] = useState<string[]>(() =>
    store.preferences.trip_theme
      ? store.preferences.trip_theme.split(', ').map((s) => s.trim()).filter(Boolean)
      : []
  );
  const [saved, setSaved] = useState(false);

  const toggleInterest = (n: string) =>
    setSelectedInterests((prev) =>
      prev.includes(n) ? prev.filter((i) => i !== n) : [...prev, n]
    );

  const handleSave = () => {
    store.setUserProfile({ name, age });
    store.setPreferences({
      ...prefs,
      trip_theme: selectedInterests.length > 0 ? selectedInterests.join(', ') : undefined,
    });
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  const isComplete = !!prefs.origin_country.trim();

  // ── Shared class helpers ──────────────────────────────────────────────────
  const inputCls =
    'w-full bg-slate-50 border border-slate-200 rounded-card px-4 py-3 text-slate-900 text-sm ' +
    'placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-colors';

  const selectedCardCls = 'border-primary bg-blue-50 ring-1 ring-primary/25';
  const defaultCardCls  = 'border-slate-200 bg-white hover:border-slate-300';

  return (
    <div className="min-h-screen bg-slate-50 py-12 px-4">
      <div className="max-w-2xl mx-auto space-y-6">

        {/* Page header */}
        <div>
          <span className="text-xs font-semibold text-primary uppercase tracking-widest">
            Your Profile
          </span>
          <h1 className="text-3xl font-extrabold text-slate-900 mt-1 tracking-tight">
            Preferences
          </h1>
          <p className="text-slate-500 mt-1 text-sm leading-relaxed">
            The AI agents use these to personalise every recommendation — visa checks,
            flight routes, accommodation type, and daily activity pacing.
          </p>
        </div>

        {/* ── 01 About You ──────────────────────────────────────────────── */}
        <div className="bg-white rounded-card border border-slate-200 shadow-sm overflow-hidden">
          <div className="px-6 py-4 border-b border-slate-100">
            <span className="text-xs font-bold text-slate-300 uppercase tracking-widest">01</span>
            <h2 className="text-base font-bold text-slate-900 mt-0.5">About You</h2>
          </div>
          <div className="px-6 py-5 space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-semibold text-slate-700 mb-1.5">
                  Name
                </label>
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="e.g. Alex"
                  className={inputCls}
                />
              </div>
              <div>
                <label className="block text-sm font-semibold text-slate-700 mb-1.5">
                  Age
                </label>
                <input
                  type="number"
                  value={age}
                  onChange={(e) => setAge(e.target.value)}
                  placeholder="e.g. 28"
                  min={1}
                  max={120}
                  className={inputCls}
                />
              </div>
            </div>
            <div>
              <label className="block text-sm font-semibold text-slate-700 mb-1.5">
                Country of Origin{' '}
                <span className="text-red-400 font-normal">*</span>
              </label>
              <input
                type="text"
                value={prefs.origin_country}
                onChange={(e) => setPrefs({ ...prefs, origin_country: e.target.value })}
                placeholder="e.g. India, United States, Germany"
                className={inputCls}
              />
              <p className="text-xs text-slate-400 mt-1.5 font-meta">
                Used to check visa requirements and find flights from your home country.
              </p>
            </div>
          </div>
        </div>

        {/* ── 02 Travel Style ───────────────────────────────────────────── */}
        <div className="bg-white rounded-card border border-slate-200 shadow-sm overflow-hidden">
          <div className="px-6 py-4 border-b border-slate-100">
            <span className="text-xs font-bold text-slate-300 uppercase tracking-widest">02</span>
            <h2 className="text-base font-bold text-slate-900 mt-0.5">Travel Style</h2>
          </div>
          <div className="px-6 py-5 space-y-6">

            {/* Budget */}
            <div>
              <label className="block text-sm font-semibold text-slate-700 mb-2.5">
                Budget Level
              </label>
              <div className="grid grid-cols-3 gap-2">
                {[
                  { value: 'budget',   label: '💰 Budget',   desc: 'Hostels, local eats' },
                  { value: 'moderate', label: '🏨 Moderate', desc: '3-star, balanced' },
                  { value: 'luxury',   label: '💎 Luxury',   desc: '5-star, fine dining' },
                ].map(({ value, label, desc }) => (
                  <button
                    key={value}
                    onClick={() => setPrefs({ ...prefs, budget_level: value as TravelPreferences['budget_level'] })}
                    className={`p-3 rounded-card border text-left transition-all ${
                      prefs.budget_level === value ? selectedCardCls : defaultCardCls
                    }`}
                  >
                    <p className="text-sm font-semibold text-slate-900">{label}</p>
                    <p className="text-xs text-slate-500 mt-0.5">{desc}</p>
                  </button>
                ))}
              </div>
            </div>

            {/* Pace */}
            <div>
              <label className="block text-sm font-semibold text-slate-700 mb-2.5">
                Travel Pace
              </label>
              <div className="grid grid-cols-3 gap-2">
                {[
                  { value: 'relaxed',  label: '🌅 Relaxed',  desc: 'Few things / day' },
                  { value: 'moderate', label: '🚶 Moderate', desc: 'Balanced itinerary' },
                  { value: 'fast',     label: '⚡ Fast',     desc: 'Pack it all in' },
                ].map(({ value, label, desc }) => (
                  <button
                    key={value}
                    onClick={() => setPrefs({ ...prefs, travel_pace: value as TravelPreferences['travel_pace'] })}
                    className={`p-3 rounded-card border text-left transition-all ${
                      prefs.travel_pace === value ? selectedCardCls : defaultCardCls
                    }`}
                  >
                    <p className="text-sm font-semibold text-slate-900">{label}</p>
                    <p className="text-xs text-slate-500 mt-0.5">{desc}</p>
                  </button>
                ))}
              </div>
            </div>

            {/* Group type + size */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
              <div>
                <label className="block text-sm font-semibold text-slate-700 mb-2.5">
                  Travelling As
                </label>
                <div className="grid grid-cols-2 gap-1.5">
                  {[
                    { value: 'solo',    label: '🧍 Solo' },
                    { value: 'couple',  label: '👫 Couple' },
                    { value: 'family',  label: '👨‍👩‍👧 Family' },
                    { value: 'friends', label: '👥 Friends' },
                  ].map(({ value, label }) => (
                    <button
                      key={value}
                      onClick={() =>
                        setPrefs({ ...prefs, travel_group_type: value as TravelPreferences['travel_group_type'] })
                      }
                      className={`py-2.5 px-3 rounded-card border text-sm font-semibold transition-all ${
                        prefs.travel_group_type === value
                          ? 'border-primary bg-blue-50 text-primary'
                          : 'border-slate-200 text-slate-600 hover:border-slate-300 bg-white'
                      }`}
                    >
                      {label}
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <label className="block text-sm font-semibold text-slate-700 mb-2.5">
                  Group Size
                </label>
                <div className="flex items-center gap-3">
                  <button
                    onClick={() =>
                      setPrefs({ ...prefs, group_size: Math.max(1, prefs.group_size - 1) })
                    }
                    className="w-10 h-10 rounded-card border border-slate-200 text-slate-700 font-bold text-lg hover:border-slate-300 bg-white transition-colors flex items-center justify-center"
                  >
                    −
                  </button>
                  <span className="text-2xl font-bold text-slate-900 w-8 text-center tabular-nums">
                    {prefs.group_size}
                  </span>
                  <button
                    onClick={() => setPrefs({ ...prefs, group_size: prefs.group_size + 1 })}
                    className="w-10 h-10 rounded-card border border-slate-200 text-slate-700 font-bold text-lg hover:border-slate-300 bg-white transition-colors flex items-center justify-center"
                  >
                    +
                  </button>
                  <span className="text-sm text-slate-500 font-medium">
                    traveller{prefs.group_size > 1 ? 's' : ''}
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* ── 03 Interests ──────────────────────────────────────────────── */}
        <div className="bg-white rounded-card border border-slate-200 shadow-sm overflow-hidden">
          <div className="px-6 py-4 border-b border-slate-100">
            <span className="text-xs font-bold text-slate-300 uppercase tracking-widest">03</span>
            <h2 className="text-base font-bold text-slate-900 mt-0.5">Your Interests</h2>
            <p className="text-sm text-slate-500 mt-0.5">
              Select everything that excites you — agents tailor activities and recommendations around these.
            </p>
          </div>
          <div className="px-6 py-5">
            <div className="flex flex-wrap gap-2">
              {INTERESTS.map(({ id, emoji, name: iName }) => {
                const isSelected = selectedInterests.includes(iName);
                return (
                  <button
                    key={id}
                    onClick={() => toggleInterest(iName)}
                    className={`flex items-center gap-1.5 px-3.5 py-2 rounded-full border text-sm font-semibold transition-all active:scale-95 ${
                      isSelected
                        ? 'bg-primary border-primary text-white shadow-sm'
                        : 'bg-white border-slate-200 text-slate-700 hover:border-primary/40 hover:text-primary'
                    }`}
                  >
                    <span aria-hidden="true">{emoji}</span>
                    {iName}
                  </button>
                );
              })}
            </div>
            {selectedInterests.length > 0 && (
              <p className="text-xs text-slate-400 mt-3 font-meta">
                {selectedInterests.length} selected
              </p>
            )}
          </div>
        </div>

        {/* ── Actions ───────────────────────────────────────────────────── */}
        <div className="flex items-center justify-between pb-8">
          <button
            onClick={onDone}
            className="px-5 py-3 rounded-card border border-slate-200 text-sm font-semibold text-slate-600 hover:bg-slate-50 transition-colors"
          >
            ← Back to planner
          </button>
          <div className="flex items-center gap-3">
            {saved && (
              <span className="text-sm text-emerald-600 font-semibold flex items-center gap-1">
                <span className="text-base">✓</span> Saved
              </span>
            )}
            <button
              onClick={handleSave}
              disabled={!isComplete}
              className="px-6 py-3 rounded-card text-sm font-semibold text-white bg-primary hover:bg-primary-dark active:scale-95 disabled:opacity-40 disabled:cursor-not-allowed transition-all shadow-sm"
            >
              Save Preferences
            </button>
          </div>
        </div>

      </div>
    </div>
  );
};
