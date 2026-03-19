"""WebSocket Connection Manager with Redis State Persistence"""

import json
import asyncio
from typing import Dict, Set, Optional
from datetime import datetime
from fastapi import WebSocket, WebSocketDisconnect
from redis.asyncio import Redis
from ..schema import TravelState, WebSocketMessage
import logging

logger = logging.getLogger(__name__)


class WebSocketManager:
    """Manages WebSocket connections and Redis state persistence"""

    def __init__(self, redis_url: str = "redis://localhost:6379"):
        self.redis_url = redis_url
        self.redis: Optional[Redis] = None
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        self.session_states: Dict[str, TravelState] = {}

    async def init_redis(self):
        """Initialize Redis connection"""
        try:
            self.redis = await Redis.from_url(self.redis_url, decode_responses=True)
            await self.redis.ping()
            logger.info("Redis connected successfully")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            self.redis = None

    async def close_redis(self):
        """Close Redis connection"""
        if self.redis:
            await self.redis.close()

    async def connect(self, session_id: str, websocket: WebSocket):
        """Register new WebSocket connection"""
        await websocket.accept()
        if session_id not in self.active_connections:
            self.active_connections[session_id] = set()
        self.active_connections[session_id].add(websocket)
        logger.info(f"Client connected to session {session_id}")

    async def disconnect(self, session_id: str, websocket: WebSocket):
        """Unregister WebSocket connection"""
        if session_id in self.active_connections:
            self.active_connections[session_id].discard(websocket)
            if not self.active_connections[session_id]:
                del self.active_connections[session_id]
        logger.info(f"Client disconnected from session {session_id}")

    async def broadcast_to_session(self, session_id: str, message: WebSocketMessage):
        """Broadcast message to all clients in a session"""
        if session_id not in self.active_connections:
            return

        message_json = json.loads(message.model_dump_json())
        disconnected = set()

        for websocket in self.active_connections[session_id]:
            try:
                await websocket.send_json(message_json)
            except Exception as e:
                logger.error(f"Error sending message: {e}")
                disconnected.add(websocket)

        # Clean up disconnected clients
        for ws in disconnected:
            await self.disconnect(session_id, ws)

    async def broadcast_thought(self, session_id: str, thought: str):
        """Broadcast agent thought to session clients"""
        message = WebSocketMessage(
            type="thought",
            data={"thought": thought}
        )
        await self.broadcast_to_session(session_id, message)

    async def broadcast_status_update(self, session_id: str, status: str, current_step: str):
        """Broadcast status update to session clients"""
        message = WebSocketMessage(
            type="status_update",
            data={
                "status": status,
                "current_step": current_step,
                "timestamp": datetime.utcnow().isoformat()
            }
        )
        await self.broadcast_to_session(session_id, message)

    async def broadcast_itinerary_ready(self, session_id: str, itinerary_json: dict):
        """Broadcast completed itinerary to session clients"""
        message = WebSocketMessage(
            type="itinerary_ready",
            data={"itinerary": itinerary_json}
        )
        await self.broadcast_to_session(session_id, message)

    async def broadcast_error(self, session_id: str, error_message: str):
        """Broadcast error message to session clients"""
        message = WebSocketMessage(
            type="error",
            data={"error": error_message}
        )
        await self.broadcast_to_session(session_id, message)

    # Redis persistence methods
    async def save_state(self, session_id: str, state: TravelState):
        """Save travel state to Redis"""
        if not self.redis:
            logger.warning("Redis not available, skipping persistence")
            return

        try:
            state_json = state.model_dump_json()
            await self.redis.setex(
                f"session:{session_id}",
                86400,  # 24-hour TTL
                state_json
            )
            logger.info(f"State saved for session {session_id}")
            self.session_states[session_id] = state
        except Exception as e:
            logger.error(f"Error saving state to Redis: {e}")

    async def load_state(self, session_id: str) -> Optional[TravelState]:
        """Load travel state from Redis"""
        if not self.redis:
            logger.warning("Redis not available, returning in-memory state")
            return self.session_states.get(session_id)

        try:
            state_json = await self.redis.get(f"session:{session_id}")
            if state_json:
                return TravelState.model_validate_json(state_json)
        except Exception as e:
            logger.error(f"Error loading state from Redis: {e}")

        return None

    async def delete_state(self, session_id: str):
        """Delete travel state from Redis"""
        if not self.redis:
            self.session_states.pop(session_id, None)
            return

        try:
            await self.redis.delete(f"session:{session_id}")
            logger.info(f"State deleted for session {session_id}")
        except Exception as e:
            logger.error(f"Error deleting state from Redis: {e}")

    async def get_all_sessions(self) -> list:
        """Get all active sessions"""
        if not self.redis:
            return list(self.active_connections.keys())

        try:
            keys = await self.redis.keys("session:*")
            return [key.replace("session:", "") for key in keys]
        except Exception as e:
            logger.error(f"Error retrieving sessions: {e}")
            return []
