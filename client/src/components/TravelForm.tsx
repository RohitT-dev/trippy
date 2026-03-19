/**
 * TravelForm - Multi-step form for gathering travel preferences
 */

import { useState } from 'react';
import { DestinationInput, TravelPreferences, FuzzyDateRange, ConfirmedDateRange } from '../store/types';

interface TravelFormProps {
  onSubmit: (data: {
    roughDates: FuzzyDateRange;
    destinations: DestinationInput[];
    preferences: TravelPreferences;
    confirmedDates?: ConfirmedDateRange;
  }) => void;
  isLoading?: boolean;
}

export const TravelForm = ({ onSubmit, isLoading = false }: TravelFormProps) => {
  const [step, setStep] = useState(1);
  const [roughDates, setRoughDates] = useState<FuzzyDateRange>({});
  const [hasDefiniteDates, setHasDefiniteDates] = useState(false);
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [destinations, setDestinations] = useState<DestinationInput[]>([]);
  const [newDest, setNewDest] = useState('');
  const [preferences, setPreferences] = useState<TravelPreferences>({
    budget_level: 'moderate',
    travel_pace: 'moderate',
    travel_group_type: 'solo',
    group_size: 1,
    origin_country: '',
  });

  const computeDurationDays = (start: string, end: string): number => {
    const ms = new Date(end).getTime() - new Date(start).getTime();
    return Math.max(1, Math.round(ms / (1000 * 60 * 60 * 24)));
  };

  const definiteDatesValid = hasDefiniteDates && startDate && endDate && endDate > startDate;

  const addDestination = () => {
    if (newDest.trim()) {
      setDestinations([
        ...destinations,
        {
          name: newDest,
          type: 'city',
          priority: destinations.length + 1,
        },
      ]);
      setNewDest('');
    }
  };

  const removeDestination = (name: string) => {
    setDestinations(destinations.filter((d) => d.name !== name));
  };

  const handleSubmit = () => {
    if (destinations.length === 0) {
      alert('Please add at least one destination');
      return;
    }
    if (!preferences.origin_country.trim()) {
      alert('Please enter your country of origin.');
      return;
    }
    if (hasDefiniteDates && !definiteDatesValid) {
      alert('Please enter a valid start and end date.');
      return;
    }
    const confirmedDates: ConfirmedDateRange | undefined =
      hasDefiniteDates && startDate && endDate
        ? {
            start_date: new Date(startDate).toISOString(),
            end_date: new Date(endDate).toISOString(),
            duration_days: computeDurationDays(startDate, endDate),
          }
        : undefined;
    onSubmit({
      roughDates,
      destinations,
      preferences: {
        ...preferences,
        trip_theme: preferences.trip_theme?.trim() || undefined,
      },
      confirmedDates,
    });
  };

  return (
    <div className="max-w-2xl mx-auto p-6 bg-white rounded-lg shadow">
      {/* Step 1: Dates */}
      {step === 1 && (
        <div className="space-y-4">
          <h2 className="text-2xl font-bold text-gray-900">When would you like to travel?</h2>

          {/* Toggle: fuzzy vs definite */}
          <div className="flex items-center gap-3 p-3 bg-gray-50 rounded-lg border border-gray-200">
            <button
              type="button"
              onClick={() => setHasDefiniteDates(false)}
              className={`flex-1 py-2 rounded-md text-sm font-medium transition-colors ${
                !hasDefiniteDates
                  ? 'bg-blue-600 text-white shadow'
                  : 'bg-white text-gray-600 border border-gray-300 hover:bg-gray-100'
              }`}
            >
              Flexible dates
            </button>
            <button
              type="button"
              onClick={() => setHasDefiniteDates(true)}
              className={`flex-1 py-2 rounded-md text-sm font-medium transition-colors ${
                hasDefiniteDates
                  ? 'bg-blue-600 text-white shadow'
                  : 'bg-white text-gray-600 border border-gray-300 hover:bg-gray-100'
              }`}
            >
              Exact dates
            </button>
          </div>

          {!hasDefiniteDates ? (
            <>
              <div>
                <label className="block text-sm font-medium text-gray-700">Preferred Season</label>
                <input
                  type="text"
                  placeholder="e.g., summer, late spring, winter"
                  value={roughDates.rough_season || ''}
                  onChange={(e) =>
                    setRoughDates({ ...roughDates, rough_season: e.target.value })
                  }
                  className="mt-1 w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-blue-500"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700">Trip Duration</label>
                <input
                  type="text"
                  placeholder="e.g., 2 weeks, 10 days, 3-4 weeks"
                  value={roughDates.rough_duration || ''}
                  onChange={(e) =>
                    setRoughDates({ ...roughDates, rough_duration: e.target.value })
                  }
                  className="mt-1 w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-blue-500"
                />
              </div>
            </>
          ) : (
            <>
              <div>
                <label className="block text-sm font-medium text-gray-700">Start Date</label>
                <input
                  type="date"
                  value={startDate}
                  min={new Date().toISOString().split('T')[0]}
                  onChange={(e) => setStartDate(e.target.value)}
                  className="mt-1 w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-blue-500"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700">End Date</label>
                <input
                  type="date"
                  value={endDate}
                  min={startDate || new Date().toISOString().split('T')[0]}
                  onChange={(e) => setEndDate(e.target.value)}
                  className="mt-1 w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-blue-500"
                />
              </div>
              {startDate && endDate && endDate > startDate && (
                <p className="text-sm text-blue-700 bg-blue-50 px-3 py-2 rounded-md">
                  {computeDurationDays(startDate, endDate)} day trip
                </p>
              )}
            </>
          )}

          <button
            onClick={() => setStep(2)}
            disabled={isLoading || (hasDefiniteDates && !definiteDatesValid)}
            className="w-full bg-blue-600 text-white py-2 rounded-md hover:bg-blue-700 disabled:bg-gray-400"
          >
            Next
          </button>
        </div>
      )}

      {/* Step 2: Destinations */}
      {step === 2 && (
        <div className="space-y-4">
          <h2 className="text-2xl font-bold text-gray-900">Where do you want to go?</h2>

          <div className="flex gap-2">
            <input
              type="text"
              placeholder="Add destination (e.g., Tokyo, Paris, Bali)"
              value={newDest}
              onChange={(e) => setNewDest(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') addDestination();
              }}
              className="flex-1 px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-blue-500"
            />
            <button
              onClick={addDestination}
              disabled={isLoading}
              className="px-4 py-2 bg-green-600 text-white rounded-md hover:bg-green-700 disabled:bg-gray-400"
            >
              Add
            </button>
          </div>

          {destinations.length > 0 && (
            <div className="space-y-2">
              {destinations.map((dest, idx) => (
                <div
                  key={idx}
                  className="flex justify-between items-center p-3 bg-blue-50 rounded-md"
                >
                  <span className="font-medium text-gray-900">{dest.name}</span>
                  <button
                    onClick={() => removeDestination(dest.name)}
                    className="text-red-600 hover:text-red-700"
                  >
                    Remove
                  </button>
                </div>
              ))}
            </div>
          )}

          <div className="flex gap-2">
            <button
              onClick={() => setStep(1)}
              disabled={isLoading}
              className="flex-1 bg-gray-300 text-gray-900 py-2 rounded-md hover:bg-gray-400 disabled:bg-gray-200"
            >
              Back
            </button>
            <button
              onClick={() => setStep(3)}
              disabled={isLoading || destinations.length === 0}
              className="flex-1 bg-blue-600 text-white py-2 rounded-md hover:bg-blue-700 disabled:bg-gray-400"
            >
              Next
            </button>
          </div>
        </div>
      )}

      {/* Step 3: Preferences */}
      {step === 3 && (
        <div className="space-y-4">
          <h2 className="text-2xl font-bold text-gray-900">Your Preferences</h2>

          {/* Origin Country */}
          <div>
            <label className="block text-sm font-medium text-gray-700">
              Departing From <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              placeholder="e.g., India, United States, Australia"
              value={preferences.origin_country}
              onChange={(e) =>
                setPreferences({ ...preferences, origin_country: e.target.value })
              }
              className="mt-1 w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-blue-500"
            />
            <p className="mt-1 text-xs text-gray-500">Used for flight search and visa requirements</p>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700">Budget Level</label>
            <select
              value={preferences.budget_level}
              onChange={(e) =>
                setPreferences({ ...preferences, budget_level: e.target.value as any })
              }
              className="mt-1 w-full px-3 py-2 border border-gray-300 rounded-md"
            >
              <option value="budget">Budget</option>
              <option value="moderate">Moderate</option>
              <option value="luxury">Luxury</option>
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700">Travel Pace</label>
            <select
              value={preferences.travel_pace}
              onChange={(e) =>
                setPreferences({ ...preferences, travel_pace: e.target.value as any })
              }
              className="mt-1 w-full px-3 py-2 border border-gray-300 rounded-md"
            >
              <option value="relaxed">Relaxed</option>
              <option value="moderate">Moderate</option>
              <option value="fast">Fast-Paced</option>
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700">Trip Theme (Optional)</label>
            <input
              type="text"
              placeholder="e.g., adventure, cultural, beach, food"
              value={preferences.trip_theme || ''}
              onChange={(e) =>
                setPreferences({ ...preferences, trip_theme: e.target.value })
              }
              className="mt-1 w-full px-3 py-2 border border-gray-300 rounded-md"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700">Travel Group</label>
            <select
              value={preferences.travel_group_type}
              onChange={(e) =>
                setPreferences({ ...preferences, travel_group_type: e.target.value as any })
              }
              className="mt-1 w-full px-3 py-2 border border-gray-300 rounded-md"
            >
              <option value="solo">Solo</option>
              <option value="couple">Couple</option>
              <option value="family">Family</option>
              <option value="friends">Friends</option>
            </select>
          </div>

          {/* Group Size */}
          <div>
            <label className="block text-sm font-medium text-gray-700">Number of Travelers</label>
            <input
              type="number"
              min={1}
              max={20}
              value={preferences.group_size}
              onChange={(e) =>
                setPreferences({ ...preferences, group_size: Math.max(1, parseInt(e.target.value) || 1) })
              }
              className="mt-1 w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-blue-500"
            />
          </div>

          <div className="flex gap-2">
            <button
              onClick={() => setStep(2)}
              disabled={isLoading}
              className="flex-1 bg-gray-300 text-gray-900 py-2 rounded-md hover:bg-gray-400"
            >
              Back
            </button>
            <button
              onClick={handleSubmit}
              disabled={isLoading}
              className="flex-1 bg-green-600 text-white py-2 rounded-md hover:bg-green-700 disabled:bg-gray-400 font-semibold"
            >
              {isLoading ? 'Processing...' : 'Create My Plan'}
            </button>
          </div>
        </div>
      )}
    </div>
  );
};
