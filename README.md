# Travel Planner - AI-Native Trip Planning Platform

An intelligent travel planning application powered by CrewAI Flows, FastAPI, and React. Let AI agents research and plan your perfect trip while streaming real-time insights to your browser.

## Features

- **AI-Powered Planning**: Specialized agents (DateScout, DestExpert, LogisticsManager) research and plan your trip
- **Fuzzy Date Support**: Input approximate travel dates like "late summer" or "2-3 weeks"
- **Real-Time Insights**: WebSocket connection streams agent thoughts as they research
- **State Persistence**: Redis stores your planning state, survives browser refreshes
- **Full Itinerary Generation**: Automatic day-by-day itinerary creation
- **Multi-Destination Support**: Plan trips across multiple cities/countries

## Tech Stack

### Backend
- **Framework**: FastAPI (Python 3.12+)
- **AI Orchestration**: CrewAI with Multi-Agent Flow
- **State Management**: Pydantic, Redis
- **Real-Time**: WebSocket for agent thought streaming

### Frontend
- **Framework**: React 18 with TypeScript
- **State Management**: Zustand with Immer
- **Styling**: Tailwind CSS
- **Build Tool**: Vite
- **API Client**: Axios

### DevOps
- **Containers**: Docker & Docker Compose
- **CI/CD**: GitHub Actions
- **Development**: Local development with hot reload

## Project Structure

```
travel-app-monorepo/
├── server/                          # Backend
│   ├── src/
│   │   ├── agents.py               # CrewAI agent definitions
│   │   ├── flow.py                 # State machine & orchestration
│   │   ├── schema.py               # Pydantic models (shared types)
│   │   ├── tools/                  # Agent tools
│   │   │   ├── date_tools.py
│   │   │   ├── destination_tools.py
│   │   │   └── logistics_tools.py
│   │   └── websocket/
│   │       └── manager.py          # WebSocket + Redis
│   ├── main.py                     # FastAPI app
│   ├── requirements.txt
│   └── .env.example
├── client/                          # Frontend
│   ├── src/
│   │   ├── components/             # React components
│   │   ├── hooks/                  # Custom hooks
│   │   ├── store/                  # Zustand stores
│   │   ├── services/               # API clients
│   │   ├── pages/                  # Page components
│   │   ├── App.tsx
│   │   └── main.tsx
│   ├── vite.config.ts
│   ├── package.json
│   └── tsconfig.json
├── docker-compose.yml              # Local development orchestration
├── Dockerfile.backend
├── .github/
│   └── workflows/
│       └── ci.yml                  # GitHub Actions CI/CD
└── README.md
```

## Quick Start

### Prerequisites
- Docker & Docker Compose (recommended)
- OR Python 3.12+ and Node.js 20+
- OpenAI API key (for CrewAI agents)

### Option 1: Docker Compose (Recommended)

```bash
# Clone the repository
git clone <repo-url>
cd trippy

# Set up environment
cp server/.env.example server/.env
cp client/.env.example client/.env

# Add your OpenAI API key to server/.env
echo "OPENAI_API_KEY=sk_your_key_here" >> server/.env

# Start all services
docker-compose up

# Access the application
# Frontend: http://localhost:5173
# Backend API: http://localhost:8000
# Redis: localhost:6379
```

### Option 2: Local Development

#### Backend Setup
```bash
cd server

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Create .env file
cp .env.example .env
# Edit .env and add your OpenAI API key

# Start Redis (separately or using Docker)
docker run -d -p 6379:6379 redis:7-alpine

# Run FastAPI server
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

#### Frontend Setup
```bash
cd ../client

# Install dependencies
npm install

# Create .env.local file
cp .env.example .env.local

# Start Vite dev server
npm run dev
```

Server will be available at `http://localhost:5173`

## API Endpoints

### REST Endpoints

```
POST   /api/plan/initialize          Initialize a new travel plan
GET    /api/plan/{session_id}        Retrieve plan state
POST   /api/plan/{session_id}/confirm Confirm refined dates
DELETE /api/plan/{session_id}        Delete a plan
GET    /health                       Health check
```

### WebSocket Endpoint

```
WS     /ws/planning/{session_id}     Real-time agent thought streaming
```

**Message Types**:
- `thought`: Agent thinking progress
- `status_update`: Status or step change
- `itinerary_ready`: Planning complete
- `error`: Error occurred
- `state_sync`: Full state synchronization

## Development

### Backend Development

```bash
cd server

# Run tests
pytest tests/ -v

# Run linter
pylint src/ main.py

# Type checking (if using mypy)
mypy src/ main.py
```

### Frontend Development

```bash
cd client

# Run dev server with HMR
npm run dev

# Build for production
npm run build

# Preview production build
npm run preview

# Lint
npm run lint
```

## Architecture Notes

### State Machine Flow
```
pending → researching → awaiting_user → finalizing → complete
  ↓
(error)
```

### CrewAI Flow
1. **DateScout**: Analyzes fuzzy dates, checks seasonal availability
2. **DestExpert**: Researches destinations, visa requirements, accommodations
3. **LogisticsManager**: Plans transportation, budgets, creates daily itinerary

### WebSocket Real-Time Updates
- Client connects to `/ws/planning/{session_id}` after initializing
- Server streams agent thoughts and status updates
- Client Zustand store updates with each message
- UI re-renders based on store changes

### State Persistence
- Redis stores TravelState JSON (24-hour TTL)
- In-memory fallback if Redis unavailable
- Frontend syncs with backend on reconnect

## Environment Variables

### Server (.env)
```
FASTAPI_ENV=development
FASTAPI_DEBUG=true
REDIS_URL=redis://localhost:6379/0
OPENAI_API_KEY=sk_your_api_key
FRONTEND_URL=http://localhost:5173
SERVER_PORT=8000
SERVER_HOST=0.0.0.0
```

### Client (.env)
```
VITE_API_URL=http://localhost:8000
VITE_WS_URL=ws://localhost:8000
```

## Deployment

### Production Checklist
- [ ] Set FASTAPI_ENV=production, FASTAPI_DEBUG=false
- [ ] Use Redis on managed service (e.g., AWS ElastiCache)
- [ ] Configure CORS properly for production domain
- [ ] Add HTTPS/TLS certificates
- [ ] Set up proper logging and monitoring
- [ ] Configure database backups for state storage
- [ ] Use environment-specific secrets management
- [ ] Run security scans before deployment

### Docker Production Build
```bash
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

## Testing

Run the CI/CD pipeline locally:
```bash
# Backend tests
cd server && pytest tests/ -v

# Frontend tests
cd ../client && npm test
```

GitHub Actions will run full pipeline on push/PR.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

MIT License - See LICENSE file for details

## Support

For issues and questions:
- GitHub Issues: [Link to issues]
- Documentation: See `/docs` folder
- Email: support@example.com

## Acknowledgments

Built with:
- [CrewAI](https://github.com/joaomdmoura/crewAI)
- [FastAPI](https://fastapi.tiangolo.com/)
- [React](https://react.dev/)
- [Zustand](https://github.com/pmndrs/zustand)
- [Tailwind CSS](https://tailwindcss.com/)
