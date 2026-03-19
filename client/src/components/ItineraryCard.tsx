/**
 * ItineraryCard - Component for displaying a single day of the itinerary
 */

import { ItineraryDay } from '../store/types';

interface ItineraryCardProps {
  day: ItineraryDay;
}

export const ItineraryCard = ({ day }: ItineraryCardProps) => {
  const dateStr = new Date(day.date).toLocaleDateString('en-US', {
    weekday: 'long',
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });

  return (
    <div className="bg-white rounded-lg shadow-md p-6 border-l-4 border-blue-600">
      <div className="flex justify-between items-start mb-4">
        <div>
          <p className="text-sm font-semibold text-blue-600">Day {day.day_number}</p>
          <h3 className="text-lg font-bold text-gray-900">{day.title}</h3>
          <p className="text-sm text-gray-600">{dateStr}</p>
        </div>
      </div>

      <div className="space-y-2">
        <p className="font-medium text-gray-700">Activities:</p>
        <ul className="space-y-1">
          {day.activities.map((activity, idx) => (
            <li key={idx} className="flex gap-2 text-gray-700">
              <span className="text-blue-600">•</span>
              <span>{activity}</span>
            </li>
          ))}
        </ul>
      </div>

      {day.notes && (
        <div className="mt-4 p-3 bg-amber-50 border border-amber-200 rounded">
          <p className="text-sm text-amber-800">
            <span className="font-semibold">Note: </span>
            {day.notes}
          </p>
        </div>
      )}
    </div>
  );
};
