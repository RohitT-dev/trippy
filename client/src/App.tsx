import { PlannerPage } from './pages/PlannerPage';
import { EventFeed } from './components/EventFeed';
import './App.css';

function App() {
  return (
    <div className="min-h-screen bg-gray-50">
      <PlannerPage />
      <div className="max-w-4xl mx-auto px-4 pb-12">
        <EventFeed className="mt-6" />
      </div>
    </div>
  );
}

export default App;
