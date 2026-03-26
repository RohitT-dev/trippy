#!/usr/bin/env python
"""FastAPI Application for Travel Planner Backend
Handles REST API endpoints and WebSocket connections
"""

import sys
from pathlib import Path

# Add server directory to Python path for src imports
sys.path.insert(0, str(Path(__file__).parent))

import uuid
import asyncio
import threading
from datetime import datetime as _dt
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocketDisconnect, WebSocket, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic_settings import BaseSettings
import logging

from src.schema import (
    TravelState,
    PlanInitializeRequest,
    PlanConfirmRequest,
    SessionResponse,
    FeedbackSubmission,
)
from src.flow import create_travel_planner_flow, TravelPlannerFlow
from src.websocket.manager import WebSocketManager
from src.callbacks import WebSocketStreamCallback
# Import listeners package so the event listener registers with CrewAI's event bus
import src.listeners as _listeners
from src.listeners import connected_clients, set_main_loop
from src.listeners.websocket_listener import broadcast
# Import feedback module — patches builtins.input on first import
import src.feedback as _feedback_mod
# Auth & database
from src.auth import init_firebase
from src.database import init_mongodb, close_mongodb
from src.users import router as users_router
from src.auth_routes import router as auth_router

# Registry of in-flight flows keyed by session_id so the feedback endpoint
# can mutate flow.state (e.g. confirmed_dates) before unblocking the thread.
_active_flows: dict[str, TravelPlannerFlow] = {}
_stopped_sessions: set[str] = set()   # sessions the user requested to stop
_flows_lock = threading.Lock()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# Settings
class Settings(BaseSettings):
    redis_url: str = "redis://localhost:6379/0"
    frontend_url: str = "http://localhost:5173"
    environment: str = "development"
    debug: bool = True
    openai_api_key: str = ""
    serper_api_key: str = ""
    brave_api_key: str = ""
    server_port: int = 8000
    server_host: str = "0.0.0.0"
    
    # LLM Settings
    llm_provider: str = "ollama"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2:3b"

    class Config:
        env_file = ".env"
        extra = "ignore"  # Ignore extra fields from .env
        case_sensitive = False  # Allow case-insensitive matching


settings = Settings()

# Global WebSocket manager
ws_manager = WebSocketManager(redis_url=settings.redis_url)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan handler for startup/shutdown"""
    # Give the event listener a reference to this event loop so it can
    # schedule coroutines from CrewAI's synchronous worker threads.
    set_main_loop(asyncio.get_running_loop())
    # Startup
    init_firebase()
    await init_mongodb()
    await ws_manager.init_redis()
    logger.info("Application started")
    yield
    # Shutdown
    await close_mongodb()
    await ws_manager.close_redis()
    logger.info("Application shutdown")


# Create app
app = FastAPI(
    title="Travel Planner API",
    description="AI-Native Travel Planning with CrewAI Flows",
    version="1.0.0",
    lifespan=lifespan
)

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url, "http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include user routes
app.include_router(users_router)
app.include_router(auth_router)


# ============================================================================
# REST API Endpoints
# ============================================================================

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "environment": settings.environment,
    }


# ============================================================================
# Real-time CrewAI Event Streaming
# ============================================================================

@app.websocket("/ws/events")
async def websocket_events(websocket: WebSocket):
    """WebSocket endpoint that streams all CrewAI events to the client."""
    await websocket.accept()
    connected_clients.append(websocket)
    logger.info("Event stream client connected (total: %d)", len(connected_clients))
    try:
        while True:
            # Keep the connection alive; we don't expect messages from the client
            # but we must await something to detect disconnection.
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.debug("Event stream WS closed: %s", exc)
    finally:
        try:
            connected_clients.remove(websocket)
        except ValueError:
            pass
        logger.info("Event stream client disconnected (total: %d)", len(connected_clients))


@app.post("/api/events/kickoff")
async def kickoff_flow(request: PlanInitializeRequest):
    """Start a CrewAI flow in a background thread and stream events via /ws/events."""
    session_id = str(uuid.uuid4())
    travel_state = TravelState(
        session_id=session_id,
        user_id=request.user_id,
        trip_description=request.trip_description,
        user_name=request.user_name,
        user_age=request.user_age,
        rough_dates=request.rough_dates,
        destinations=request.destinations,
        preferences=request.preferences,
        confirmed_dates=request.confirmed_dates,
        ui_status="pending",
        current_step="gathering_inputs",
    )

    flow = await create_travel_planner_flow(travel_state)

    # Register a feedback slot BEFORE the thread starts so input() is ready immediately
    _feedback_mod.register_session(session_id)

    # Store the live flow so the feedback endpoint can update its state
    with _flows_lock:
        _active_flows[session_id] = flow

    def _run():
        _feedback_mod.set_thread_session(session_id)
        try:
            flow.kickoff()
        except Exception as exc:
            # Don't broadcast an error if the user explicitly stopped the flow
            with _flows_lock:
                was_stopped = session_id in _stopped_sessions
            if was_stopped:
                logger.info("Flow stopped by user for session %s", session_id)
            else:
                logger.error("Flow kickoff error: %s", exc, exc_info=True)
                broadcast({
                    "type": "flow_error",
                    "session_id": session_id,
                    "data": {
                        "error": str(exc),
                        "session_id": session_id,
                    },
                    "timestamp": _dt.utcnow().isoformat(),
                })
        finally:
            _feedback_mod.cleanup_session(session_id)
            with _flows_lock:
                _active_flows.pop(session_id, None)
                _stopped_sessions.discard(session_id)

    thread = threading.Thread(target=_run, daemon=True, name=f"flow-{session_id[:8]}")
    thread.start()
    logger.info("Flow started in background thread for session %s", session_id)
    return {"status": "started", "session_id": session_id}


@app.post("/api/plan/initialize", response_model=SessionResponse)
async def initialize_plan(request: PlanInitializeRequest):
    """
    Initialize a new travel planning session.

    This endpoint:
    1. Creates a new session ID
    2. Initializes TravelState with user inputs
    3. Saves state to Redis
    4. Returns session info for WebSocket connection

    Client should then connect to WebSocket endpoint with returned session_id.
    """
    try:
        session_id = str(uuid.uuid4())

        # Create initial travel state
        travel_state = TravelState(
            session_id=session_id,
            user_id=request.user_id,
            trip_description=request.trip_description,
            user_name=request.user_name,
            user_age=request.user_age,
            rough_dates=request.rough_dates,
            destinations=request.destinations,
            preferences=request.preferences,
            confirmed_dates=request.confirmed_dates,
            ui_status="pending",
            current_step="gathering_inputs"
        )

        # Save to Redis
        await ws_manager.save_state(session_id, travel_state)

        logger.info(f"Travel planning session initialized: {session_id}")
        
        # Run flow directly (no websocket)
        logger.info(f"Starting CrewAI flow for session {session_id}")
        
        # Create flow instance without callback handler
        flow = await create_travel_planner_flow(travel_state, callback_handler=None)
        
        # Run the flow (this will execute all agents)
        await asyncio.to_thread(flow.kickoff)
        
        # Get updated state from flow
        updated_state = flow.get_state()
        
        # Save final state
        await ws_manager.save_state(session_id, updated_state)
        
        logger.info(f"Flow completed successfully for session {session_id}")

        return SessionResponse(
            session_id=session_id,
            state=updated_state
        )

    except Exception as e:
        logger.error(f"Error initializing plan: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/plan/{session_id}", response_model=SessionResponse)
async def get_plan(session_id: str):
    """Retrieve a travel plan by session ID"""
    try:
        state = await ws_manager.load_state(session_id)

        if not state:
            raise HTTPException(status_code=404, detail="Session not found")

        return SessionResponse(session_id=session_id, state=state)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving plan: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/plan/{session_id}/feedback")
async def submit_human_feedback(session_id: str, body: FeedbackSubmission):
    """Submit human feedback for a paused @human_feedback step.

    If *selected_dates* is provided (user picked a date option), the flow's
    confirmed_dates is updated first so research_destinations uses the right
    window before the flow thread is unblocked.
    """
    # Apply the user-selected date window to the live flow state
    if body.selected_dates is not None:
        with _flows_lock:
            active_flow = _active_flows.get(session_id)
        if active_flow is not None:
            active_flow.state.confirmed_dates = body.selected_dates
            logger.info(
                "Updated confirmed_dates for session %s: %s → %s",
                session_id,
                body.selected_dates.start_date.date(),
                body.selected_dates.end_date.date(),
            )

    success = _feedback_mod.submit_feedback(session_id, body.feedback_text)
    if not success:
        raise HTTPException(
            status_code=404,
            detail="No pending feedback request found for this session.",
        )
    logger.info("Human feedback accepted for session %s", session_id)
    return {"status": "accepted", "session_id": session_id}


@app.post("/api/plan/{session_id}/stop")
async def stop_flow(session_id: str):
    """Request cancellation of an in-flight planning flow.

    Marks the session as stopped and unblocks any pending human-feedback
    wait so the background thread exits cleanly.  A `flow_stopped` event
    is broadcast so the frontend can update its UI immediately.
    """
    with _flows_lock:
        is_active = session_id in _active_flows
        _stopped_sessions.add(session_id)

    if not is_active:
        raise HTTPException(status_code=404, detail="No active flow for this session.")

    # Unblock any human_feedback wait so the thread can exit
    _feedback_mod.submit_feedback(session_id, "__stop__")

    broadcast({
        "type": "flow_stopped",
        "session_id": session_id,
        "data": {"session_id": session_id, "message": "Flow stopped by user."},
        "timestamp": _dt.utcnow().isoformat(),
    })
    logger.info("Stop requested for session %s", session_id)
    return {"status": "stopping", "session_id": session_id}
async def confirm_dates(session_id: str, request: PlanConfirmRequest):
    """Confirm refined dates for a travel plan"""
    try:
        state = await ws_manager.load_state(session_id)

        if not state:
            raise HTTPException(status_code=404, detail="Session not found")

        # Update confirmed dates
        state.confirmed_dates = request.confirmed_dates
        state.ui_status = "researching"
        state.current_step = "running_agents"

        # Save updated state
        await ws_manager.save_state(session_id, state)

        # Notify connected clients
        await ws_manager.broadcast_status_update(
            session_id,
            state.ui_status,
            state.current_step
        )

        logger.info(f"Dates confirmed for session {session_id}")

        return {"status": "dates confirmed", "session_id": session_id}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error confirming dates: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/plan/{session_id}")
async def delete_plan(session_id: str):
    """Delete a travel plan session"""
    try:
        await ws_manager.delete_state(session_id)
        logger.info(f"Session deleted: {session_id}")
        return {"status": "deleted", "session_id": session_id}
    except Exception as e:
        logger.error(f"Error deleting plan: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Error Handlers
# ============================================================================

@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail}
    )


@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    logger.error(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )


# ============================================================================
# Main
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    import os
    
    # Ensure we're running from the server directory for proper module resolution
    server_dir = Path(__file__).parent
    os.chdir(server_dir)
    
    # Get port from command line argument or use default
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000

    uvicorn.run(
        "main:app",  # Use import string to enable reload
        host="0.0.0.0",
        port=port,
        reload=settings.debug,
        log_level="info"
    )
